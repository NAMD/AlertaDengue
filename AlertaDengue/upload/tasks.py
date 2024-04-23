import os
from pathlib import Path
from django.core.mail import send_mail

import pandas as pd
import geopandas as gpd
import dask.dataframe as dd
from loguru import logger
from simpledbf import Dbf5
from celery import shared_task
from celery.result import AsyncResult, allow_join_result
from psycopg2.extras import DictCursor

from django.utils.translation import gettext_lazy as _
from django.conf import settings

from ad_main.settings import get_sqla_conn
from .models import SINAN, Status
from .sinan.utils import (
    EXPECTED_FIELDS,
    UF_CODES,
    sinan_drop_duplicates_from_dataframe,
    sinan_parse_fields,
    chunk_gen,
    add_dv,
)

CODES_UF = {v: k for k, v in UF_CODES.items()}

DB_ENGINE = get_sqla_conn(database="dengue")


@shared_task
def sinan_split_by_uf_or_chunk(
    file_path: str,
    dest_dir: Path,
    by_uf: bool
) -> bool:
    file = Path(file_path)

    if not file.exists():
        raise FileNotFoundError(f"{file} not found")

    dest_dir.mkdir(exist_ok=True)

    if file.suffix.lower() in [".csv", ".csv.gz"]:
        columns = pd.read_csv(
            str(file.absolute()),
            encoding="iso-8859-1",
            index_col=0,
            nrows=0,
        ).columns.to_list()

        for chunk, df in enumerate(pd.read_csv(
            str(file),
            chunksize=30000,
            encoding="iso-8859-1",
            usecols=list(
                set(EXPECTED_FIELDS.values()) & set(columns)
            ),  # pyright: ignore
        )):
            if by_uf:
                for _, row in df.iterrows():
                    _append_row_to_uf(row, dest_dir)
            else:
                df.to_parquet(os.path.join(
                    str(dest_dir), f"{str(file)}-{chunk}.parquet"
                ))

        return True

    if file.suffix.lower() == ".dbf":
        dbf = Dbf5(str(file), codec="iso-8859-1")

        for chunk, (lowerbound, upperbound) in enumerate(
            chunk_gen(30000, dbf.numrec)
        ):
            df = gpd.read_file(
                str(file),
                include_fields=list(
                    set(EXPECTED_FIELDS.values()) & set(dbf.columns)
                ),
                rows=slice(lowerbound, upperbound),
                ignore_geometry=True,
            )

            if by_uf:
                for _, row in df.iterrows():
                    _append_row_to_uf(row, dest_dir)
            else:
                df.to_parquet(os.path.join(
                    str(dest_dir), f"{str(file)}-{chunk}.parquet"
                ))

        return True

    if file.suffix.lower() == ".parquet":
        columns = pd.read_parquet(
            str(file.absolute()),
            engine="fastparquet",
            encoding="iso-8859-1",
            index_col=0,
            nrows=0,
        ).columns.to_list()

        for chunk, df in enumerate(
            pd.read_parquet(
                str(file),
                engine="fastparquet",
                encoding="iso-8859-1",
                usecols=list(
                    set(EXPECTED_FIELDS.values()) & set(columns)
                ),  # pyright: ignore
                chunksize=30000
            )
        ):
            if by_uf:
                for _, row in df.iterrows():
                    _append_row_to_uf(row, dest_dir)
            else:
                df.to_parquet(os.path.join(
                    str(dest_dir), f"{str(file)}-{chunk}.parquet"
                ))

        return True

    raise ValueError(f"Unable to parse file type '{file.suffix}'")


def _append_row_to_uf(row: pd.Series, dest_dir: Path) -> None:
    try:
        uf = CODES_UF[int(str(row['ID_MUNICIP'])[:2])]
    except (TypeError, ValueError, KeyError) as e:
        print(str(e))
        uf = "BR"

    uf_file = dest_dir / f"{uf}.csv.gz"

    row.to_csv(uf_file, mode="a", index=False)


@shared_task
def process_sinan_file(sinan_pk: int) -> bool:
    sinan = SINAN.objects.get(pk=sinan_pk)
    fpath = Path(str(sinan.filepath))

    try:
        if fpath.suffix.lower() == ".csv":
            result: AsyncResult = chunk_csv_file.delay(  # pyright: ignore
                sinan.pk
            )

        elif fpath.suffix.lower() == ".dbf":
            result: AsyncResult = chunk_dbf_file.delay(  # pyright: ignore
                sinan.pk
            )

        elif fpath.suffix.lower() == ".parquet":
            result: AsyncResult = chunk_parquet_file.delay(  # pyright: ignore
                sinan.pk
            )

        else:
            err = f"Unknown file type {fpath.suffix}"
            logger.error(err)
            sinan.status = Status.ERROR
            sinan.status_error = err
            sinan.save(update_fields=['status', 'status_error'])
            return False

    except Exception as e:
        sinan.status = Status.ERROR
        sinan.status_error = f"Error chunking file: {e}"
        sinan.save(update_fields=['status', 'status_error'])
        return False

    with allow_join_result():
        try:
            chunking_success = result.get(timeout=10*60)

            if chunking_success:
                logger.info(
                    f"Parsed {len(list(Path(str(sinan.chunks_dir)).glob('*.parquet')))} "
                    f"chunks for {sinan.filename}"
                )

                inserted: AsyncResult = (
                    parse_insert_chunks_on_database.delay(  # pyright: ignore
                        sinan_pk
                    )
                )

                if inserted.get(timeout=10*60):
                    return True
            if result.status == "FAILURE":
                logger.error(f"Chunking task for {sinan.filename} failed")
            return False

        except Exception as e:
            err = f"Process file task failed with exception: {e}"
            logger.error(err)
            sinan.status = Status.ERROR
            sinan.status_error = str(err)
            sinan.save(update_fields=['status', 'status_error'])
            return False


@shared_task
def chunk_csv_file(sinan_pk: int) -> bool:
    sinan = SINAN.objects.get(pk=sinan_pk)

    if sinan.status == Status.WAITING_CHUNK:
        sinan.status = Status.CHUNKING
        sinan.save(update_fields=['status'])

        logger.info("Converting CSV file to Parquet chunks")

        if not os.path.exists(str(sinan.filepath)):
            raise FileNotFoundError(f"{str(sinan.filepath)} does not exist")

        for chunk, df in enumerate(
            pd.read_csv(
                str(sinan.filepath),
                usecols=list(EXPECTED_FIELDS.values()),  # pyright: ignore
                chunksize=10000
            )
        ):
            df.to_parquet(os.path.join(
                str(sinan.chunks_dir), f"{sinan.filename}-{chunk}.parquet"
            ))

        sinan.status = Status.WAITING_INSERT
        sinan.save(update_fields=['status'])
        return True
    else:
        logger.info(
            f"Invalid Status to chunk SINAN object: {sinan.status}"
        )
        return False


@shared_task
def chunk_dbf_file(sinan_pk: int) -> bool:
    sinan = SINAN.objects.get(pk=sinan_pk)

    if sinan.status == Status.WAITING_CHUNK:
        sinan.status = Status.CHUNKING
        sinan.save(update_fields=['status'])

        logger.info("Converting DBF file to Parquet chunks")
        dbf = Dbf5(str(sinan.filepath), codec="iso-8859-1")
        dbf_name = str(dbf.dbf)[:-4]

        if not os.path.exists(str(sinan.filepath)):
            raise FileNotFoundError(f"{str(sinan.filepath)} does not exist")

        for chunk, (lowerbound, upperbound) in enumerate(
            chunk_gen(10000, dbf.numrec)
        ):
            parquet_fname = os.path.join(
                str(sinan.chunks_dir), f"{dbf_name}-{chunk}.parquet"
            )
            df = gpd.read_file(
                str(sinan.filepath),
                include_fields=list(EXPECTED_FIELDS.values()),
                rows=slice(lowerbound, upperbound),
                ignore_geometry=True,
            )

            df.to_parquet(parquet_fname)

        sinan.status = Status.WAITING_INSERT
        sinan.save(update_fields=['status'])
        return True
    else:
        logger.info(
            f"Invalid Status to chunk SINAN object: {sinan.status}"
        )
        return False


@shared_task
def chunk_parquet_file(sinan_pk: int) -> bool:
    sinan = SINAN.objects.get(pk=sinan_pk)

    if sinan.status == Status.WAITING_CHUNK:
        sinan.status = Status.CHUNKING
        sinan.save(update_fields=['status'])

        logger.info("Converting Parquet file into chunks")

        if not os.path.exists(str(sinan.filepath)):
            raise FileNotFoundError(f"{str(sinan.filepath)} does not exist")

        for chunk, df in enumerate(
            pd.read_parquet(
                str(sinan.filepath),
                engine="fastparquet",
                encoding="iso-8859-1",
                usecols=list(EXPECTED_FIELDS.values()),  # pyright: ignore
                chunksize=10000
            )
        ):
            df.to_parquet(os.path.join(
                str(sinan.chunks_dir), f"{sinan.filename}-{chunk}.parquet"
            ))

        sinan.status = Status.WAITING_INSERT
        sinan.save(update_fields=['status'])
        return True
    else:
        logger.info(
            f"Invalid Status to chunk SINAN object: {sinan.status}"
        )
        return False


@shared_task
def parse_insert_chunks_on_database(sinan_pk: int) -> bool:
    sinan = SINAN.objects.get(pk=sinan_pk)

    misparsed_csv_file = (
        Path(str(settings.DBF_SINAN)) / "residue_csvs" /
        f"RESIDUE_{Path(str(sinan.filename)).with_suffix('.csv')}"
    )

    misparsed_csv_file.touch()

    if sinan.status == Status.WAITING_INSERT:
        sinan.misparsed_file = str(misparsed_csv_file.absolute())
        sinan.status = Status.INSERTING
        sinan.save(update_fields=['misparsed_file', 'status'])

        uploaded_rows = sinan_insert_chunks_on_database(sinan.pk)
        sinan.inserted_rows = uploaded_rows

        if uploaded_rows:
            logger.info(
                f"Inserting {uploaded_rows} rows from {sinan.filename}"
            )

            if sinan.parse_error:
                sinan.status = Status.FINISHED_MISPARSED
                sinan.save(update_fields=['status', 'inserted_rows'])
                # send_mail() # TODO: send mail with link to misparsed csv file
                return True
            else:
                sinan.status = Status.FINISHED
                if misparsed_csv_file:
                    misparsed_csv_file.unlink(missing_ok=True)
                    sinan.misparsed_file = None
                sinan.save(
                    update_fields=['status', 'misparsed_file', 'inserted_rows']
                )
                # send_mail(): # TODO: send successful insert email
                return True
        else:
            ...
            # send_mail(): # TODO: send failed insert email
    else:
        logger.error(f"Invalid SINAN Status for parsing: {sinan.status}")

    return False


def sinan_insert_chunks_on_database(sinan_pk: int) -> int:
    sinan = SINAN.objects.get(pk=sinan_pk)

    chunks_list = list(Path(str(sinan.chunks_dir)).glob("*.parquet"))

    uploaded_rows: int = 0
    with DB_ENGINE.begin() as conn:  # pyright: ignore
        # TODO: this could be ran asynchronously
        for chunk in chunks_list:
            try:
                df: dd = dd.read_parquet(  # pyright: ignore
                    str(chunk.absolute()),
                    engine="fastparquet"
                )
            except Exception as e:
                err = f"Error reading chunks for {sinan.filename}: {e}"
                logger.error(err)
                if sinan.misparsed_file:
                    Path(str(sinan.misparsed_file)).unlink(missing_ok=True)
                    sinan.misparsed_file = None
                sinan.status = Status.ERROR
                sinan.status_error = err
                sinan.save(
                    update_fields=['status', 'misparsed_file', 'status_error']
                )
                return 0

            try:
                df = sinan_drop_duplicates_from_dataframe(
                    df.compute(),  # pyright: ignore
                    sinan.filename
                )
            except Exception as e:
                err = f"Error dropping duplicates from {sinan.filename}: {e}"
                logger.error(err)
                sinan.status = Status.ERROR
                sinan.status_error = err
                sinan.save(update_fields=['status', 'status_error'])
                return 0

            # Can't throw any exception. Return False instead
            df = sinan_parse_fields(
                df,  # pyright: ignore
                sinan
            )

            # Can't throw any exception. Return number of inserted rows
            uploaded_rows += save_to_pgsql(
                df,  # pyright: ignore
                sinan,
                conn
            )
    return uploaded_rows


def save_to_pgsql(
    df: pd.DataFrame, sinan_obj: SINAN, conn
) -> int:
    """
    Return the number of rows executed by INSERT. Can't throw any Exception
    """
    try:
        cursor = conn.connection.cursor(cursor_factory=DictCursor)

        expected_cols = {v: k for k, v in EXPECTED_FIELDS.items()}
        cols = [expected_cols[c] for c in list(df.columns)]

        insert_sql = (
            f"INSERT INTO {sinan_obj.table_schema}"
            f"({','.join(cols)}) VALUES ({','.join(['%s' for _ in cols])}) "
            f"ON CONFLICT ON CONSTRAINT casos_unicos DO UPDATE SET "
            f"{','.join([f'{j}=excluded.{j}' for j in cols])}"
        )

        rows = [
            tuple(row)
            for row in df.itertuples(index=False)
        ]

        cursor.executemany(insert_sql, rows)
        conn.connection.commit()
        return len(df)
    except Exception as e:
        conn.connection.rollback()
        err = (
            f"Error inserting {sinan_obj.filename} chunk in database."
            f"Error: {str(e)}"
        )
        logger.error(err)
        sinan_obj.status = Status.ERROR
        sinan_obj.status_error = err
        sinan_obj.parse_error = False
        sinan_obj.save(update_fields=['status', 'status_error', 'parse_error'])
        return 0
