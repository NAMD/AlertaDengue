import pandas as pd
from ad_main.settings import get_sqla_conn

DB_ENGINE = get_sqla_conn(database="infodengue")


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

    with DB_ENGINE.connect() as conn:
        data = conn.execute(sql).fetchall()
        return pd.DataFrame(data)
