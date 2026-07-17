-- ============================================================
-- Deskie Lead Intelligence Engine — Initial Schema
-- Run this against your local PostgreSQL database
-- ============================================================

-- Create database (run separately as superuser if needed)
-- CREATE DATABASE deskie_lie;

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── businesses ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS businesses (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT        NOT NULL,
    category      TEXT        NOT NULL,
    city          TEXT        NOT NULL,
    phone         TEXT,
    website       TEXT,
    address       TEXT,
    rating        NUMERIC(3,1),
    review_count  INTEGER,
    opening_hours JSONB,
    social_links  JSONB       DEFAULT '{}',
    place_id      TEXT        UNIQUE,
    source        TEXT        DEFAULT 'google_places',
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_businesses_city     ON businesses(city);
CREATE INDEX IF NOT EXISTS idx_businesses_category ON businesses(category);
CREATE INDEX IF NOT EXISTS idx_businesses_place_id ON businesses(place_id);

-- ── research_results ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS research_results (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id   UUID        NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    agent_name    TEXT        NOT NULL,
    result_json   JSONB       NOT NULL,
    status        TEXT        DEFAULT 'success',
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_business_id ON research_results(business_id);
CREATE INDEX IF NOT EXISTS idx_research_agent_name  ON research_results(agent_name);

-- ── lead_scores ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lead_scores (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id          UUID        NOT NULL UNIQUE REFERENCES businesses(id) ON DELETE CASCADE,
    pain_score           NUMERIC(5,2),
    pain_breakdown       JSONB,
    business_value_score NUMERIC(5,2),
    value_breakdown      JSONB,
    digital_score        NUMERIC(5,2),
    digital_breakdown    JSONB,
    timing_score         NUMERIC(5,2),
    timing_breakdown     JSONB,
    final_score          NUMERIC(5,2),
    priority             TEXT,
    scored_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scores_final_score ON lead_scores(final_score DESC);
CREATE INDEX IF NOT EXISTS idx_scores_priority    ON lead_scores(priority);

-- ── lead_reports ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lead_reports (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    business_id       UUID        NOT NULL UNIQUE REFERENCES businesses(id) ON DELETE CASCADE,
    summary           TEXT,
    top_reasons       JSONB,
    pain_points       JSONB,
    recommended_pitch TEXT,
    evidence          JSONB,
    generated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── updated_at trigger ───────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS set_updated_at ON businesses;
CREATE TRIGGER set_updated_at
    BEFORE UPDATE ON businesses
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
