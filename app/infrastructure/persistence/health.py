from sqlalchemy import Engine, text


def check_database(engine: Engine) -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1 FROM organizations LIMIT 1"))
