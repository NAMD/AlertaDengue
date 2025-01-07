from typing import Literal, Optional, Union, Generator
from pathlib import Path
from datetime import date
from array import array
import pickle

from epiweeks import Week

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from chunked_upload.models import BaseChunkedUpload

from dados.models import City
from .sinan.utils import UF_CODES, chunk_gen


User = get_user_model()


def sinan_upload_path() -> str:
    return str(Path(settings.DBF_SINAN) / "imported")


def sinan_upload_log_path() -> str:
    return str(Path(settings.DBF_SINAN) / "log")


class SINANChunkedUpload(BaseChunkedUpload):
    user = models.ForeignKey(
        User,
        related_name='uploads',
        on_delete=models.PROTECT
    )


class SINANUploadLogStatus(models.Model):
    STATUS = [
        (0, "Pending"),
        (1, "Success"),
        (2, "Error")
    ]

    LOG_LEVEL = ["DEBUG", "PROGRESS", "INFO", "WARNING", "ERROR", "SUCCESS"]

    status = models.IntegerField(choices=STATUS, default=0, null=False)
    log_file = models.FilePathField(path=sinan_upload_log_path)
    inserts_file = models.FilePathField(path=sinan_upload_log_path, null=True)
    updates_file = models.FilePathField(path=sinan_upload_log_path, null=True)

    @property
    def inserts(self) -> int:
        inserts_file = Path(sinan_upload_log_path()) / f"{self.pk}.inserts.log"

        if not inserts_file.exists():
            return 0

        with inserts_file.open("rb") as log:
            inserts = pickle.load(log)

        return len(inserts)

    def inserts_ids(
        self, chunk_size: int = 100000
    ) -> Generator[list[int], None, None]:
        inserts_file = Path(sinan_upload_log_path()) / f"{self.pk}.inserts.log"

        if not inserts_file.exists():
            return iter([])

        with inserts_file.open("rb") as log:
            inserts = pickle.load(log)

        for start, end in chunk_gen(chunk_size, len(inserts)):
            yield inserts[start:end]

    @property
    def updates(self) -> int:
        updates_file = Path(sinan_upload_log_path()) / f"{self.pk}.updates.log"

        if not updates_file.exists():
            return 0

        with updates_file.open("rb") as log:
            updates = pickle.load(log)

        return len(updates)

    def updates_ids(
        self, chunk_size: int = 100000
    ) -> Generator[list[int], None, None]:
        updates_file = Path(sinan_upload_log_path()) / f"{self.pk}.updates.log"

        if not updates_file.exists():
            return iter([])

        with updates_file.open("rb") as log:
            updates = pickle.load(log)

        for start, end in chunk_gen(chunk_size, len(updates)):
            yield updates[start:end]

    @property
    def time_spend(self) -> float:
        for log in self.read_logs(level="DEBUG"):
            if "time_spend: " in log:
                _, time_spend = log.split("time_spend: ")
                return float(time_spend)
        raise ValueError("No time_spend found in logs")

    def write_inserts(self, insert_ids: list[int]):
        log_dir = Path(sinan_upload_log_path())
        inserts_file = log_dir / f"{self.pk}.inserts.log"
        inserts_file.touch()
        inserts = array("i", insert_ids)
        with inserts_file.open("wb") as log:
            pickle.dump(inserts, log)
        self.inserts_file = inserts_file
        self.save()

    def write_updates(self, updates_ids: list[int]):
        log_dir = Path(sinan_upload_log_path())
        updates_file = log_dir / f"{self.pk}.updates.log"
        updates_file.touch()
        updates = array("i", updates_ids)
        with updates_file.open("wb") as log:
            pickle.dump(updates, log)
        self.updates_file = updates_file
        self.save()

    def read_logs(
        self,
        level: Optional[Literal[
            "DEBUG", "PROGRESS", "INFO", "WARNING", "ERROR", "SUCCESS"
        ]] = None,
        only_level: bool = False,
    ):
        with Path(self.log_file).open(mode='r', encoding="utf-8") as log_file:
            logs = []

            for line in log_file:
                if level:
                    startswith = (
                        tuple(self.LOG_LEVEL[self.LOG_LEVEL.index(level):])
                        if not only_level else level
                    )
                    if line.startswith(startswith):
                        logs.append(line.strip())
                else:
                    logs.append(line.strip())
        return logs

    def _write_logs(
        self,
        level: Literal["DEBUG", "PROGRESS", "INFO", "WARNING", "ERROR", "SUCCESS"],
        message: str,
    ):
        if self.status != 0:
            raise ValueError(
                "Log is closed for writing (finished with status " +
                f"{self.status})."
            )
        log_message = f"{level}{' ' * (7 - len(level))} - {message}\n"
        with Path(self.log_file).open(mode='a', encoding="utf-8") as log_file:
            log_file.write(log_message)

    def debug(self, message: str):
        self._write_logs(level="DEBUG", message=message)

    def progress(self, rowcount: int, total_rows: int):
        percentage = f"{min((rowcount / total_rows) * 100, 100):.2f}%"
        self._write_logs(level="PROGRESS", message=percentage)

    def info(self, message: str):
        self._write_logs(level="INFO", message=message)

    def warning(self, message: str):
        self._write_logs(level="WARNING", message=message)

    def fatal(self, error_message: str):
        self._write_logs(level="ERROR", message=error_message)
        self.status = 2
        self.save()

    def done(self, inserts: int, time_spend: float):
        filename = SINANUpload.objects.get(status__id=self.id).upload.filename
        message = f"{filename}: {inserts} inserts in {time_spend:.2f} seconds."
        self._write_logs(level="SUCCESS", message=message)
        self.status = 1
        self.save()


class SINANUpload(models.Model):
    UFs = [
        (None, "Brasil"),
        ("AC", "Acre"),
        ("AL", "Alagoas"),
        ("AP", "Amapá"),
        ("AM", "Amazonas"),
        ("BA", "Bahia"),
        ("CE", "Ceará"),
        ("DF", "Distrito Federal"),
        ("ES", "Espírito Santo"),
        ("GO", "Goiás"),
        ("MA", "Maranhão"),
        ("MT", "Mato Grosso"),
        ("MS", "Mato Grosso do Sul"),
        ("MG", "Minas Gerais"),
        ("PA", "Pará"),
        ("PB", "Paraíba"),
        ("PR", "Paraná"),
        ("PE", "Pernambuco"),
        ("PI", "Piauí"),
        ("RJ", "Rio de Janeiro"),
        ("RN", "Rio Grande do Norte"),
        ("RS", "Rio Grande do Sul"),
        ("RO", "Rondônia"),
        ("RR", "Roraima"),
        ("SC", "Santa Catarina"),
        ("SP", "São Paulo"),
        ("SE", "Sergipe"),
        ("TO", "Tocantins"),
    ]

    CID10 = [
        ("A90", "Dengue"),
        ("A92.0", "Chikungunya"),
        ("A928", "Zika")
    ]

    REQUIRED_COLS = [
        "ID_MUNICIP",
        "ID_AGRAVO",
        "DT_SIN_PRI",
        "DT_NOTIFIC",
        "DT_DIGITA",
        "DT_NASC",
        "NU_ANO",
        "NU_IDADE_N",
        "NU_NOTIFIC",
        "SEM_NOT",
        "SEM_PRI",
        "CS_SEXO",
    ]

    SYNONYMS_FIELDS = {"ID_MUNICIP": ["ID_MN_RESI"]}

    COLUMNS = {
        "DT_NOTIFIC": "dt_notific",
        "SEM_NOT": "se_notif",
        "NU_ANO": "ano_notif",
        "DT_SIN_PRI": "dt_sin_pri",
        "SEM_PRI": "se_sin_pri",
        "DT_DIGITA": "dt_digita",
        "ID_MUNICIP": "municipio_geocodigo",
        "NU_NOTIFIC": "nu_notific",
        "ID_AGRAVO": "cid10_codigo",
        "DT_NASC": "dt_nasc",
        "CS_SEXO": "cs_sexo",
        "NU_IDADE_N": "nu_idade_n",
        "RESUL_PCR_": "resul_pcr",
        "CRITERIO": "criterio",
        "CLASSI_FIN": "classi_fin",
        # updated on 12-2024
        "DT_CHIK_S1": "dt_chik_s1",
        "DT_CHIK_S2": "dt_chik_s2",
        "DT_PRNT": "dt_prnt",
        "RES_CHIKS1": "res_chiks1",
        "RES_CHIKS2": "res_chiks2",
        "RESUL_PRNT": "resul_prnt",
        "DT_SORO": "dt_soro",
        "RESUL_SORO": "resul_soro",
        "DT_NS1": "dt_ns1",
        "RESUL_NS1": "resul_ns1",
        "DT_VIRAL": "dt_viral",
        "RESUL_VI_N": "resul_vi_n",
        "DT_PCR": "dt_pcr",
        "SOROTIPO": "sorotipo",
        "ID_DISTRIT": "id_distrit",
        "ID_BAIRRO": "id_bairro",
        "NM_BAIRRO": "nm_bairro",
        "ID_UNIDADE": "id_unidade",
    }

    cid10 = models.CharField(max_length=5, null=False, choices=CID10)
    uf = models.CharField(max_length=2, null=True, choices=UFs)
    year = models.IntegerField(null=False)
    upload = models.ForeignKey(
        SINANChunkedUpload,
        on_delete=models.PROTECT,
        null=True,
    )
    status = models.ForeignKey(
        SINANUploadLogStatus,
        on_delete=models.PROTECT,
        null=True,
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.upload.filename}"

    def _final_basename(self):
        filename = str(Path(self.upload.filename).with_suffix(""))
        disease = {
            "A90": "DENG",
            "A92.0": "CHIK",
            "A928": "ZIKA"
        }
        uf = self.uf if self.uf else "BR"
        epiweek = Week.fromdate(self.uploaded_at)
        return "_".join(
            [str(epiweek), disease[self.cid10], uf]
        ) + "-" + filename

    class Meta:
        app_label = "upload"


class SINANUploadFatalError(Exception):
    def __init__(self, log_status: SINANUploadLogStatus, error_message: str):
        try:
            log_status.fatal(error_message)
        except ValueError:
            pass
        super().__init__(error_message)
