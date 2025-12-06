export type Trend = 'increasing' | 'stable' | 'decreasing' | 'unknown'
export type RiskLevel = 'low' | 'medium' | 'high' | 'unknown'

export interface FinancialHealth {
  available: boolean
  reason?: string | null
  company_name?: string | null
  ticker?: string | null
  cik?: string | null
  key_indicators?: {
    revenue_trend?: Trend
    net_income_trend?: Trend
    liquidity_risk?: RiskLevel
    going_concern_flag?: boolean
  }
  raw?: Record<string, unknown>
}

export interface ComplianceLegal {
  available: boolean
  reason?: string | null
  inspections_count?: number
  violations_count?: number
  total_penalties_usd?: number
  last_inspection_date?: string | null
  risk_indicator?: RiskLevel
  raw?: Record<string, unknown>
}

export interface OperationalResilience {
  available: boolean
  reason?: string | null
  region?: {
    state?: string | null
    county?: string | null
    fips?: string | null
  }
  hazard_profile?: {
    flood_risk?: RiskLevel
    storm_risk?: RiskLevel
    wildfire_risk?: RiskLevel
    other_events_last_5_years?: number
  }
  overall_operational_disruption_risk?: RiskLevel
  raw?: Record<string, unknown>
}

export interface EsgReputation {
  available: boolean
  reason?: string | null
  facilities_found?: number
  recent_violations?: number
  total_penalties_usd?: number
  last_violation_date?: string | null
  program_flags?: {
    air?: boolean
    water?: boolean
    waste?: boolean
  }
  esg_risk_indicator?: RiskLevel
  raw?: Record<string, unknown>
}

export interface DeepRiskResponse {
  financial_health: FinancialHealth
  compliance_legal: ComplianceLegal
  operational_resilience: OperationalResilience
  esg_reputation: EsgReputation
}
