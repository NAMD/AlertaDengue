import pandas as pd
from ad_main.settings import get_sqla_conn

db_engine = get_sqla_conn(database="DBF")


def is_partner_active():
    """
    :param: name, contact, email
        where status is True
    :return: pandas dataframe
    """
    sql = """
      SELECT name, contact, email FROM dbf_sendtoPartner
      WHERE status = 'True'
      ORDER BY name
    """

    with db_engine.connect() as conn:
        return pd.read_sql(sql, conn)
