import os
from pathlib import Path
from typing import Optional

import owncloud
import pandas as pd
import geopandas as gpd
import dask.dataframe as dd
import pyarrow.parquet as pq
from loguru import logger
from simpledbf import Dbf5
from celery import shared_task
from celery.result import AsyncResult, allow_join_result
from psycopg2.extras import DictCursor
from sqlalchemy.engine import Engine

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
)

CODES_UF = {v: k for k, v in UF_CODES.items()}

DB_ENGINE = get_sqla_conn(database="dengue")


@shared_task(default_retry_delay=30, max_retries=3, soft_time_limit=5*60)
def sinan_split_by_uf_or_chunk(
    file_path: str,
    dest_dir: str,
    by_uf: bool
) -> tuple[bool, Optional[list[str]]]:
    """
    TODO: Split & async it
    """
    file = Path(file_path)
    dest = Path(dest_dir)
    task_ids: list[str] = []

    if not file.exists():
        raise FileNotFoundError(f"{file} not found")

    def semaphore(
        chunk_df: pd.DataFrame,
        chunk_id: int,
        task_ids: list[str] = []
    ) -> None:
        if by_uf:
            uf_rows: dict[str, list[pd.Series]] = {}
            for _, row in chunk_df.iterrows():
                try:
                    uf = CODES_UF[int(str(row['ID_MUNICIP'])[:2])]
                except (TypeError, ValueError, KeyError):
                    uf = "BR"
                if uf not in uf_rows:
                    uf_rows[uf] = []
                uf_rows[uf].append(row)

            for uf, rows in uf_rows.items():
                uf_file = dest / f"{uf}.csv"

                df = pd.DataFrame(rows)

                df.to_csv(
                    str(uf_file),
                    index=False,
                    mode='a',
                    header=not uf_file.exists()
                )
            file.unlink()

        else:
            parquet_chunk = os.path.join(
                dest_dir,
                f"{os.path.splitext(file.name)[0]}-{chunk_id}.parquet"
            )
            chunk_df.to_parquet(str(parquet_chunk))
            by_uf_task = sinan_split_by_uf_or_chunk.delay(
                file_path=str(parquet_chunk),
                dest_dir=dest_dir,
                by_uf=True
            )
            task_ids.append(by_uf_task.id)

    if file.suffix.lower() in [".csv", ".csv.gz"]:
        header_df = pd.read_csv(
            str(file.absolute()),
            encoding="iso-8859-1",
            index_col=0,
            nrows=10,
        )

        header_df = header_df.reset_index(drop=False)

        columns = header_df.columns.to_list()

        for chunk, df in enumerate(pd.read_csv(
            str(file),
            chunksize=30000,
            encoding="iso-8859-1",
            usecols=list(
                set(EXPECTED_FIELDS.values()) & set(columns)
            ),
        )):
            semaphore(df, chunk, task_ids)

    elif file.suffix.lower() == ".dbf":
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
            semaphore(df, chunk, task_ids)

    elif file.suffix.lower() == ".parquet":
        table = pq.read_table(str(file.absolute()))
        columns = table.column_names

        for chunk, (lowerbound, upperbound) in enumerate(
            chunk_gen(30000, len(table))
        ):
            df = table.slice(lowerbound, upperbound).to_pandas()
            semaphore(df, chunk, task_ids)

    else:
        raise ValueError(f"Unable to parse file type '{file.suffix}'")

    if not by_uf:
        file.unlink()
        return True, task_ids
    return True, None


@shared_task(default_retry_delay=30, max_retries=3, soft_time_limit=5*60)
def process_sinan_file(sinan_pk: int) -> bool:
    sinan = SINAN.objects.get(pk=sinan_pk)
    fpath = Path(str(sinan.filepath))

    try:
        result: AsyncResult
        if fpath.suffix.lower() == ".csv":
            result = chunk_csv_file.delay(
                sinan.pk
            )

        elif fpath.suffix.lower() == ".dbf":
            result = chunk_dbf_file.delay(
                sinan.pk
            )

        elif fpath.suffix.lower() == ".parquet":
            result = chunk_parquet_file.delay(
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
            chunking_success = result.get(timeout=120*60)

            if chunking_success:
                inserted: AsyncResult = (
                    parse_insert_chunks_on_database.delay(  # pyright: ignore
                        sinan_pk
                    )
                )

                if inserted.get(timeout=120*60):
                    return True
            if result.status == "FAILURE":
                err = f"Chunking task for {sinan.filename} failed"
                logger.error(err)
                sinan.status = Status.ERROR
                sinan.status_error = str(err)
                sinan.save(update_fields=['status', 'status_error'])
            return False

        except Exception as e:
            err = f"Process file task failed with exception: {e}"
            logger.error(err)
            sinan.status = Status.ERROR
            sinan.status_error = str(err)
            sinan.save(update_fields=['status', 'status_error'])
            return False


@shared_task(default_retry_delay=30, max_retries=3, soft_time_limit=3*60)
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
                # usecols=list(EXPECTED_FIELDS.values()),
                chunksize=10000,
                encoding="iso-8859-1",
            )
        ):
            missing_cols = (
                set(EXPECTED_FIELDS.values()).difference(set(df.columns))
            )
            for col in missing_cols:
                df[col] = None
            df.to_parquet(os.path.join(
                str(sinan.chunks_dir), f"{sinan.filename}-{chunk}.parquet"
            ))

        sinan.status = Status.WAITING_INSERT
        sinan.save(update_fields=['status'])
        return True


@shared_task(default_retry_delay=30, max_retries=3, soft_time_limit=3*60)
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
                # include_fields=list(EXPECTED_FIELDS.values()),
                rows=slice(lowerbound, upperbound),
                ignore_geometry=True,
            )

            missing_cols = (
                set(EXPECTED_FIELDS.values()).difference(set(df.columns))
            )

            for col in missing_cols:
                df[col] = None

            df.to_parquet(parquet_fname)

        sinan.status = Status.WAITING_INSERT
        sinan.save(update_fields=['status'])
        return True


@shared_task(default_retry_delay=30, max_retries=3, soft_time_limit=3*60)
def chunk_parquet_file(sinan_pk: int) -> bool:
    sinan = SINAN.objects.get(pk=sinan_pk)

    if sinan.status == Status.WAITING_CHUNK:
        sinan.status = Status.CHUNKING
        sinan.save(update_fields=['status'])

        logger.info("Converting Parquet file into chunks")

        if not os.path.exists(str(sinan.filepath)):
            raise FileNotFoundError(f"{str(sinan.filepath)} does not exist")

        table = pq.read_table(str(sinan.filepath))

        for chunk, (lowerbound, upperbound) in enumerate(
            chunk_gen(30000, len(table))
        ):
            df = table.slice(lowerbound, upperbound).to_pandas()

            missing_cols = (
                set(EXPECTED_FIELDS.values()).difference(set(df.columns))
            )
            for col in missing_cols:
                df[col] = None

            df.to_parquet(os.path.join(
                str(sinan.chunks_dir), f"{sinan.filename}-{chunk}.parquet"
            ))

        sinan.status = Status.WAITING_INSERT
        sinan.save(update_fields=['status'])
        return True


@shared_task(default_retry_delay=30, max_retries=3, soft_time_limit=120*60)
def parse_insert_chunks_on_database(sinan_pk: int) -> bool:
    sinan = SINAN.objects.get(pk=sinan_pk)

    misparsed_csv_file = (
        Path(str(settings.DBF_SINAN)) / "residue_csvs" /
        f"RESIDUE_{sinan.id}_{Path(str(sinan.filename)).with_suffix('.csv')}"
    )

    misparsed_csv_file.touch()

    if sinan.status == Status.WAITING_INSERT:
        sinan.misparsed_file = str(misparsed_csv_file.absolute())
        sinan.status = Status.INSERTING
        sinan.save(update_fields=['misparsed_file', 'status'])

        uploaded_rows = sinan_insert_chunks_on_database(sinan)
        sinan.inserted_rows = uploaded_rows

        if uploaded_rows is None:
            return False

        if sinan.parse_error:
            sinan.status = Status.FINISHED_MISPARSED
            sinan.save(update_fields=['status', 'inserted_rows'])
            # send_mail() # TODO: send mail with link to misparsed csv file
            return True

        sinan.status = Status.FINISHED
        if misparsed_csv_file:
            misparsed_csv_file.unlink(missing_ok=True)
            sinan.misparsed_file = None
        sinan.save(
            update_fields=['status', 'misparsed_file', 'inserted_rows']
        )
        # send_mail(): # TODO: send successful insert email
        return True


def sinan_insert_chunks_on_database(sinan: SINAN) -> int | None:
    chunks_list = (
        list(Path(str(sinan.chunks_dir))
             .glob(f"{sinan.filename}*.parquet"))
    )

    uploaded_rows: int = 0
    with DB_ENGINE.begin() as conn:
        # TODO: this could be ran asynchronously
        for chunk in chunks_list:
            try:
                df: dd = dd.read_parquet(  # type: ignore
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
                return None

            try:
                df = sinan_drop_duplicates_from_dataframe(
                    df.compute(),  # type: ignore
                    sinan.filename + f"_{sinan.id}"
                )
            except Exception as e:
                err = f"Error dropping duplicates from {sinan.filename}: {e}"
                logger.error(err)
                sinan.status = Status.ERROR
                sinan.status_error = err
                sinan.save(update_fields=['status', 'status_error'])
                return None

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

        logger.info(f"Inserting {uploaded_rows} rows from {sinan.filename}")
    return uploaded_rows


def save_to_pgsql(
    df: pd.DataFrame, sinan_obj: SINAN, conn: Engine
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


@shared_task(default_retry_delay=30, max_retries=3, soft_time_limit=5*60)
def owncloud_download_file(
    username: str,
    password: str,
    file_path: str,
    output_path: str
) -> bool | None:
    try:
        oc = owncloud.Client(settings.OWNCLOUD_URL)
        oc.login(username, password)
        return bool(oc.get_file(file_path, output_path))
    except (owncloud.HTTPResponseError, AttributeError):
        return False
    finally:
        oc.logout()
