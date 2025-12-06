/**
 * @typedef {import('../types/deepRisk').FinancialHealth} FinancialHealth
 * @typedef {import('../types/deepRisk').ComplianceLegal} ComplianceLegal
 * @typedef {import('../types/deepRisk').OperationalResilience} OperationalResilience
 * @typedef {import('../types/deepRisk').EsgReputation} EsgReputation
 */

const currencyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
})

const formatCurrency = (value) => {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—'
  return currencyFormatter.format(value)
}

const formatNumber = (value) => {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—'
  return value.toLocaleString()
}

const RiskSectionCard = ({ title, loading, error, data, children }) => {
  const isUnavailable = data && data.available === false
  const hasContent = data && data.available !== false

  return (
    <div className="risk-section-card">
      <h4>{title}</h4>
      {loading && <p className="muted">Deep search running...</p>}
      {!loading && error && <p className="muted error-inline">{error}</p>}
      {!loading && !error && !data && <p className="muted">Run a deep search to view details.</p>}
      {!loading && !error && isUnavailable && (
        <p className="muted">{data.reason || 'No records were returned for this supplier.'}</p>
      )}
      {!loading && !error && hasContent && children}
    </div>
  )
}

export const FinancialHealthPanel = ({ loading, error, data }) => {
  return (
    <RiskSectionCard title="Financial Health" loading={loading} error={error} data={data}>
      <div className="panel-field">
        <span className="label">Company</span>
        <p>{data?.company_name || 'Unknown'}</p>
      </div>
      <div className="panel-field-columns">
        <div>
          <span className="label">Ticker</span>
          <p>{data?.ticker || '—'}</p>
        </div>
        <div>
          <span className="label">CIK</span>
          <p>{data?.cik || '—'}</p>
        </div>
      </div>
      <div className="panel-field">
        <span className="label">Revenue trend</span>
        <p>{data?.key_indicators?.revenue_trend || 'unknown'}</p>
      </div>
      <div className="panel-field">
        <span className="label">Net income trend</span>
        <p>{data?.key_indicators?.net_income_trend || 'unknown'}</p>
      </div>
      <div className="panel-field-columns">
        <div>
          <span className="label">Liquidity</span>
          <p>{data?.key_indicators?.liquidity_risk || 'unknown'}</p>
        </div>
        <div>
          <span className="label">Going concern</span>
          <p>{data?.key_indicators?.going_concern_flag ? 'Flagged' : 'No flag'}</p>
        </div>
      </div>
    </RiskSectionCard>
  )
}

export const ComplianceLegalPanel = ({ loading, error, data }) => {
  return (
    <RiskSectionCard title="Compliance & Legal" loading={loading} error={error} data={data}>
      <div className="panel-field-columns">
        <div>
          <span className="label">Inspections</span>
          <p>{formatNumber(data?.inspections_count)}</p>
        </div>
        <div>
          <span className="label">Violations</span>
          <p>{formatNumber(data?.violations_count)}</p>
        </div>
      </div>
      <div className="panel-field">
        <span className="label">Penalties (lifetime)</span>
        <p>{formatCurrency(data?.total_penalties_usd)}</p>
      </div>
      <div className="panel-field">
        <span className="label">Last inspection</span>
        <p>{data?.last_inspection_date || 'Unknown'}</p>
      </div>
      <div className="panel-field">
        <span className="label">Risk indicator</span>
        <p>{data?.risk_indicator || 'unknown'}</p>
      </div>
    </RiskSectionCard>
  )
}

export const OperationalResiliencePanel = ({ loading, error, data }) => {
  return (
    <RiskSectionCard title="Operational Resilience" loading={loading} error={error} data={data}>
      <div className="panel-field">
        <span className="label">Region</span>
        <p>
          {data?.region?.county ? `${data.region.county}, ` : ''}
          {data?.region?.state || 'Unknown'}
        </p>
      </div>
      <div className="panel-field-columns">
        <div>
          <span className="label">Flood risk</span>
          <p>{data?.hazard_profile?.flood_risk || 'unknown'}</p>
        </div>
        <div>
          <span className="label">Storm risk</span>
          <p>{data?.hazard_profile?.storm_risk || 'unknown'}</p>
        </div>
      </div>
      <div className="panel-field-columns">
        <div>
          <span className="label">Wildfire risk</span>
          <p>{data?.hazard_profile?.wildfire_risk || 'unknown'}</p>
        </div>
        <div>
          <span className="label">Events (5y)</span>
          <p>{formatNumber(data?.hazard_profile?.other_events_last_5_years)}</p>
        </div>
      </div>
      <div className="panel-field">
        <span className="label">Overall disruption risk</span>
        <p>{data?.overall_operational_disruption_risk || 'unknown'}</p>
      </div>
    </RiskSectionCard>
  )
}

export const EsgReputationPanel = ({ loading, error, data }) => {
  const hasPrograms = Boolean(
    data?.program_flags?.air || data?.program_flags?.water || data?.program_flags?.waste,
  )

  return (
    <RiskSectionCard title="ESG & Reputation" loading={loading} error={error} data={data}>
      <div className="panel-field-columns">
        <div>
          <span className="label">Facilities</span>
          <p>{formatNumber(data?.facilities_found)}</p>
        </div>
        <div>
          <span className="label">Violations</span>
          <p>{formatNumber(data?.recent_violations)}</p>
        </div>
      </div>
      <div className="panel-field">
        <span className="label">Penalties (lifetime)</span>
        <p>{formatCurrency(data?.total_penalties_usd)}</p>
      </div>
      <div className="panel-field">
        <span className="label">Last violation</span>
        <p>{data?.last_violation_date || 'Unknown'}</p>
      </div>
      <div className="panel-field">
        <span className="label">Program coverage</span>
        {hasPrograms ? (
          <div className="program-flags">
            <span className={data?.program_flags?.air ? 'pill active' : 'pill'}>Air</span>
            <span className={data?.program_flags?.water ? 'pill active' : 'pill'}>Water</span>
            <span className={data?.program_flags?.waste ? 'pill active' : 'pill'}>Waste</span>
          </div>
        ) : (
          <p>Not available</p>
        )}
      </div>
      <div className="panel-field">
        <span className="label">ESG risk indicator</span>
        <p>{data?.esg_risk_indicator || 'unknown'}</p>
      </div>
    </RiskSectionCard>
  )
}
