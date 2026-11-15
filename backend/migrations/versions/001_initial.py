from alembic import op

revision = "001"
down_revision = None


def upgrade():
    op.execute("""
    CREATE TABLE users(login text PRIMARY KEY,name text NOT NULL,role text NOT NULL,password text NOT NULL,
      CHECK(role IN ('FINANCIAL_ANALYST','DATA_ANALYST','DATA_ENGINEER','DATA_STEWARD','ADMIN')));
    CREATE TABLE sessions(token_digest text PRIMARY KEY,login text REFERENCES users,expires timestamptz NOT NULL);
    CREATE TABLE checkpoints(source text PRIMARY KEY,sequence bigint NOT NULL DEFAULT 0,last_success timestamptz,last_error text);
    INSERT INTO checkpoints(source) VALUES ('erp'),('bank'),('fx'),('csv');
    CREATE TABLE runs(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),request uuid NOT NULL,actor text REFERENCES users,
      started timestamptz NOT NULL,finished timestamptz NOT NULL DEFAULT clock_timestamp(),mode text NOT NULL,
      status text NOT NULL,contract text NOT NULL DEFAULT 'source/1',summary jsonb NOT NULL);
    CREATE TABLE raw(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,source text NOT NULL REFERENCES checkpoints,
      sequence bigint NOT NULL,entity text NOT NULL,external_id text NOT NULL,revision int NOT NULL,
      event_time timestamptz NOT NULL,received timestamptz NOT NULL DEFAULT clock_timestamp(),hash text NOT NULL,
      payload jsonb NOT NULL,run uuid NOT NULL REFERENCES runs, disposition text NOT NULL,
      UNIQUE(source,sequence));
    CREATE INDEX raw_version ON raw(source,entity,external_id,revision DESC,id);
    CREATE TABLE mapping(version int PRIMARY KEY,aliases jsonb NOT NULL,actor text REFERENCES users,created timestamptz NOT NULL DEFAULT now());
    INSERT INTO mapping VALUES (1,'{}',NULL);
    CREATE TABLE quality(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,run uuid NOT NULL REFERENCES runs,raw bigint REFERENCES raw,
      source text NOT NULL,dimension text NOT NULL,code text NOT NULL,detail jsonb NOT NULL,created timestamptz NOT NULL DEFAULT now());
    CREATE TABLE stage(raw bigint NOT NULL REFERENCES raw,mapping int NOT NULL REFERENCES mapping,normalized jsonb,
      status text NOT NULL,reason text,run uuid NOT NULL REFERENCES runs,PRIMARY KEY(raw,mapping));
    CREATE TABLE facts(source text NOT NULL,entity text NOT NULL,external_id text NOT NULL,revision int NOT NULL,
      raw bigint NOT NULL REFERENCES raw,mapping int NOT NULL REFERENCES mapping,run uuid NOT NULL REFERENCES runs,
      business_date date, amount numeric(22,2),currency text,category text,attributes jsonb NOT NULL,
      PRIMARY KEY(source,entity,external_id));
    CREATE INDEX fact_period ON facts(entity,business_date);
    CREATE VIEW fact_invoices AS SELECT * FROM facts WHERE entity='invoice';
    CREATE VIEW fact_payments AS SELECT * FROM facts WHERE entity='payment';
    CREATE VIEW fact_budgets AS SELECT * FROM facts WHERE entity='budget';
    CREATE VIEW dim_counterparties AS SELECT external_id,attributes,raw FROM facts WHERE entity='partner';
    CREATE VIEW dim_rates AS SELECT business_date,currency,attributes,raw FROM facts WHERE entity='rate';
    CREATE TABLE reports(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),start_date date NOT NULL,end_date date NOT NULL,
      actor text NOT NULL REFERENCES users,method text NOT NULL,manifest jsonb NOT NULL,result jsonb NOT NULL,
      checksum text NOT NULL UNIQUE,quality text NOT NULL,created timestamptz NOT NULL DEFAULT now());
    CREATE TABLE scenarios(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),report uuid NOT NULL REFERENCES reports,
      actor text NOT NULL REFERENCES users,assumptions jsonb NOT NULL,result jsonb NOT NULL,created timestamptz NOT NULL DEFAULT now());
    CREATE TABLE audit(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,actor text REFERENCES users,request uuid NOT NULL,
      action text NOT NULL,subject text NOT NULL,detail jsonb NOT NULL,created timestamptz NOT NULL DEFAULT now());
    CREATE FUNCTION immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Immutable data' USING ERRCODE='23514'; END $$;
    CREATE TRIGGER freeze_raw BEFORE UPDATE OR DELETE ON raw FOR EACH ROW EXECUTE FUNCTION immutable();
    CREATE TRIGGER freeze_reports BEFORE UPDATE OR DELETE ON reports FOR EACH ROW EXECUTE FUNCTION immutable();
    CREATE TRIGGER freeze_mapping BEFORE UPDATE OR DELETE ON mapping FOR EACH ROW EXECUTE FUNCTION immutable();
    CREATE TRIGGER freeze_audit BEFORE UPDATE OR DELETE ON audit FOR EACH ROW EXECUTE FUNCTION immutable();
    """)


def downgrade():
    op.execute(
        "DROP VIEW dim_rates,dim_counterparties,fact_budgets,fact_payments,fact_invoices"
    )
    op.execute(
        "DROP TABLE audit,scenarios,reports,facts,stage,quality,mapping,raw,runs,checkpoints,sessions,users CASCADE"
    )
    op.execute("DROP FUNCTION immutable()")
