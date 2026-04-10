-- Enable UUID generation.
-- gen_random_uuid() is a built-in PostgreSQL function.
-- It generates a random UUID like "a8098c1a-f86e-11da-bd1a-00112444be1e".
-- We use UUIDs instead of auto-increment integers because:
--   1. They are globally unique — safe to generate in multiple places.
--   2. They do not leak how many records exist (no sequential IDs).
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- One row per business session.
-- For this MVP there is one business. Sprint 2 adds auth and multiple businesses.
CREATE TABLE IF NOT EXISTS businesses (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL,
  industry      TEXT NOT NULL,
  state         TEXT NOT NULL,
  business_type TEXT NOT NULL,
  employee_count INTEGER NOT NULL,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- One row per chat message (both user messages and AI replies).
CREATE TABLE IF NOT EXISTS messages (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id   UUID REFERENCES businesses(id) ON DELETE CASCADE NOT NULL,
  -- ON DELETE CASCADE means: if the business row is deleted,
  -- all its messages are automatically deleted too.
  -- Without this, deleting a business would leave orphaned messages
  -- with a business_id pointing to nothing — broken data.
  role          TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  -- CHECK constraint: PostgreSQL enforces this at the database level.
  -- Even if Flask has a bug and sends "admin", the DB rejects it.
  -- Defense in depth — validate at the app layer AND the DB layer.
  content       TEXT NOT NULL,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Index so fetching all messages for a business is fast.
-- Without this index, PostgreSQL scans every row in the messages table.
-- With it, PostgreSQL jumps directly to the right rows.
-- Rule of thumb: any column you filter or sort by frequently needs an index.
CREATE INDEX IF NOT EXISTS messages_business_id_idx ON messages(business_id);
