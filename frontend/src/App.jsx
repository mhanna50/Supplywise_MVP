import { useMemo, useState } from 'react'
import { assessSupplier, runDeepRisk, searchSuppliers } from './api/client'
import {
  ComplianceLegalPanel,
  EsgReputationPanel,
  FinancialHealthPanel,
  OperationalResiliencePanel,
} from './components/DeepRiskPanels'

/**
 * @typedef {import('./types/deepRisk').DeepRiskResponse} DeepRiskResponse
 */

const DebugPanel = ({ title, data }) => {
  const [open, setOpen] = useState(false)

  if (data === null || data === undefined) return null

  return (
    <div className="debug-panel">
      <button className="debug-toggle" onClick={() => setOpen((prev) => !prev)}>
        <span>{title}</span>
        <span>{open ? '-' : '+'}</span>
      </button>
      {open && <pre>{JSON.stringify(data, null, 2)}</pre>}
    </div>
  )
}

const formatAddress = (business = {}) => {
  if (!business || typeof business !== 'object') return ''

  const rawAddress = typeof business.address === 'object' ? business.address : null
  const partLine = [rawAddress?.streetNumber, rawAddress?.streetName].filter(Boolean).join(' ').trim()
  const rawLine1 = rawAddress?.freeformAddress || (partLine ? partLine : null)
  const line1 = typeof business.address === 'string' ? business.address : rawLine1

  const city = business.city || rawAddress?.municipality
  const state = business.state || rawAddress?.countrySubdivision
  const postalCode = business.postalCode || rawAddress?.postalCode
  const country = business.country || rawAddress?.countryCodeISO3 || rawAddress?.countryCode

  const segments = [line1, city, state, postalCode, country]
  return segments.filter(Boolean).join(', ')
}

const getWebsiteUrl = (business = {}) => {
  if (!business || typeof business !== 'object') return ''
  const poi = business.poi || business.raw?.poi || business.azure_result?.poi || {}
  const website = business.website || business.url || poi?.url || poi?.website
  if (!website || typeof website !== 'string') return ''
  return website.trim()
}

const getWebsiteHref = (website) => {
  if (!website) return ''
  if (/^https?:\/\//i.test(website)) return website
  return `https://${website}`
}

const getPhoneNumber = (business = {}) => {
  if (!business || typeof business !== 'object') return ''
  const poi = business.poi || business.raw?.poi || business.azure_result?.poi || {}
  const phone = business.phone || poi?.phone || poi?.phoneNumber
  if (!phone || typeof phone !== 'string') return ''
  return phone.trim()
}

const getPhoneHref = (phone) => {
  if (!phone) return ''
  const digits = phone.replace(/[^0-9+]/g, '')
  return digits ? `tel:${digits}` : ''
}

const formatGleifAddress = (summary = {}) => {
  const legal = (summary && summary.legal_address) || {}
  const segments = [legal.line1, legal.city, legal.postal_code, legal.country]
  const formatted = segments.filter(Boolean).join(', ')
  return formatted || 'Not available'
}

const riskAccent = (score) => {
  if (typeof score !== 'number') return 'medium'
  if (score >= 80) return 'low'
  if (score >= 50) return 'medium'
  return 'high'
}

const splitSegments = (input = '') => {
  const segments = []
  let buffer = ''
  let inQuotes = false

  for (const char of input) {
    if (char === '"') {
      inQuotes = !inQuotes
      continue
    }

    if (!inQuotes && char === ',') {
      if (buffer.trim()) segments.push(buffer.trim())
      buffer = ''
      continue
    }

    buffer += char
  }

  if (buffer.trim()) segments.push(buffer.trim())
  return segments
}

const parseSearchInput = (input = '') => {
  const segments = splitSegments(input)
  if (!segments.length) return { query: '', filters: {} }

  const [primary, ...rest] = segments
  const filters = {}
  if (rest[0]) filters.city = rest[0]
  if (rest[1]) filters.state = rest[1]
  if (rest[2]) filters.country = rest[2]

  return {
    query: primary,
    filters,
  }
}

function App() {
  const [searchInput, setSearchInput] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [azureRaw, setAzureRaw] = useState(null)
  const [assessment, setAssessment] = useState(null)
  const [hasEntered, setHasEntered] = useState(false)
  const [deepRisk, setDeepRisk] = useState(/** @type {DeepRiskResponse | null} */ (null))
  const [deepRiskLoading, setDeepRiskLoading] = useState(false)
  const [deepRiskError, setDeepRiskError] = useState(null)
  const [pendingAssessmentKey, setPendingAssessmentKey] = useState(null)
  const [loadingSearch, setLoadingSearch] = useState(false)
  const [loadingAssessment, setLoadingAssessment] = useState(false)
  const [error, setError] = useState('')

  const handleSearch = async (event) => {
    event.preventDefault()
    const { query, filters } = parseSearchInput(searchInput)

    if (!query.trim()) {
      setError('Enter a business name, industry, or location to search.')
      return
    }

    setError('')
    setLoadingSearch(true)
    setAssessment(null)
    setDeepRisk(null)
    setDeepRiskError(null)
    setPendingAssessmentKey(null)

    try {
      const data = await searchSuppliers(query, filters)

      if (data.error) {
        setError(data.error)
      } else {
        setError('')
      }

      const limitedResults = (data.results || []).slice(0, 10)
      setSearchResults(limitedResults)
      setAzureRaw(data.raw_azure_response)
    } catch (err) {
      setError(err.message || 'Unable to fetch suppliers right now.')
    } finally {
      setLoadingSearch(false)
    }
  }

  const handleAnalyze = async (business) => {
    setLoadingAssessment(true)
    setDeepRiskLoading(true)
    setError('')
    setDeepRiskError(null)
    setDeepRisk(null)
    const targetKey = business.id || business.name || null
    setPendingAssessmentKey(targetKey)

    const azureAddress = (business.raw && business.raw.address) || {}
    const payload = {
      id: business.id,
      name: business.name,
      address: business.address,
      city: business.city || azureAddress?.municipality || azureAddress?.localName,
      state: business.state || azureAddress?.countrySubdivision,
      country: business.country || azureAddress?.countryCodeISO3 || azureAddress?.countryCode,
      postalCode: business.postalCode || azureAddress?.postalCode,
      latitude: business.latitude,
      longitude: business.longitude,
      score: business.score,
      phone: business.phone,
      website: business.website,
      county: business.county || azureAddress?.countrySecondarySubdivision,
      azure_result: business.raw,
    }

    try {
      const [assessmentResult, deepRiskResult] = await Promise.allSettled([
        assessSupplier(payload),
        runDeepRisk(payload),
      ])

      if (assessmentResult.status === 'fulfilled') {
        setAssessment(assessmentResult.value)
        setError('')
      } else {
        const reason = assessmentResult.reason
        setAssessment(null)
        setError(reason?.message || 'Unable to score this supplier.')
      }

      if (deepRiskResult.status === 'fulfilled') {
        setDeepRisk(deepRiskResult.value)
        setDeepRiskError(null)
      } else {
        const reason = deepRiskResult.reason
        setDeepRisk(null)
        setDeepRiskError(reason?.message || 'Failed to run deep search.')
      }
    } catch (err) {
      setAssessment(null)
      setDeepRisk(null)
      setError(err.message || 'Unable to score this supplier.')
      setDeepRiskError(err.message || 'Failed to run deep search.')
    } finally {
      setLoadingAssessment(false)
      setDeepRiskLoading(false)
      setPendingAssessmentKey(null)
    }
  }

  const assessmentFactors = useMemo(() => {
    if (!assessment?.risk_factors) return []
    return Object.entries(assessment.risk_factors)
  }, [assessment])

  const assessedBusiness = assessment?.business || null
  const gleifSummary = assessment?.gleif_enriched || null
  const assessedWebsite = assessedBusiness ? getWebsiteUrl(assessedBusiness) : ''
  const assessedPhone = assessedBusiness ? getPhoneNumber(assessedBusiness) : ''
  const assessedWebsiteHref = assessedWebsite ? getWebsiteHref(assessedWebsite) : ''
  const assessedPhoneHref = assessedPhone ? getPhoneHref(assessedPhone) : ''

  if (!hasEntered) {
    return (
      <div className="splash-overlay">
        <div className="splash-card">
          <div className="brand">SupplyWise</div>
          <h1>Early Access Preview</h1>
          <p>
            SupplyWise helps you explore suppliers, connect Azure Maps intelligence with GLEIF data, and run
            deep-risk analyses across financial health, compliance, operational resilience, and ESG vectors.
          </p>
          <p>
            This preview is a work in progress: APIs, scoring models, and UX will evolve rapidly as we expand data
            coverage, add automation, and move toward production readiness.
          </p>
          <p>
            In the near future we&apos;ll introduce richer supplier profiles, workflow integrations, and automated
            watchlists—but for now you&apos;re seeing an early, hands-on glimpse of what&apos;s coming.
          </p>
          <button className="primary" onClick={() => setHasEntered(true)}>
            Enter the prototype
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="app-shell">
      <header className="top-bar">
        <div className="brand">SupplyWise</div>
        <p>Rapid supplier risk scoring</p>
      </header>

      <main className="content">
        <section className="card">
          <h2>Search suppliers</h2>
          <form className="search-form" onSubmit={handleSearch}>
            <label htmlFor="supplier-search">Business, industry, or location</label>
            <div className="search-bar">
              <input
                id="supplier-search"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder='"Acme, Inc", Seattle, WA, US'
              />
              <button className="primary" type="submit" disabled={loadingSearch}>
                {loadingSearch ? 'Searching...' : 'Search'}
              </button>
            </div>
            <span className="input-hint">Add optional city, state, and country using commas. Put quotes around names that include commas.</span>
          </form>
          {error && <div className="error-banner">{error}</div>}
        </section>

        <section className="card">
          <h3>Results</h3>
          {loadingSearch && <p className="muted">Looking up suppliers...</p>}
          {!loadingSearch && searchResults.length === 0 && <p className="muted">No suppliers yet. Run a search to get started.</p>}
          <div className="results-grid">
            {searchResults.map((result) => {
              const resultKey = result.id || result.name
              const assessedKey = assessment?.business?.id || assessment?.business?.name
              const assessedName = assessment?.business?.name
              const websiteUrl = getWebsiteUrl(result)
              const phoneNumber = getPhoneNumber(result)
              const websiteHref = websiteUrl ? getWebsiteHref(websiteUrl) : ''
              const phoneHref = phoneNumber ? getPhoneHref(phoneNumber) : ''
              const isAnalyzingThis = Boolean(
                loadingAssessment &&
                  pendingAssessmentKey &&
                  resultKey &&
                  pendingAssessmentKey === resultKey,
              )
              const isSelected = Boolean(
                (assessedKey && resultKey && assessedKey === resultKey) ||
                  (assessedName && result.name && assessedName === result.name),
              ) || isAnalyzingThis
              return (
                <div key={result.id || result.name} className={`result-card ${isSelected ? 'selected' : ''}`}>
                  <div>
                    <h4>{result.name || 'Unnamed business'}</h4>
                    <p>{formatAddress(result)}</p>
                    {(websiteHref || phoneHref) && (
                      <div className="contact-links">
                        {websiteHref && (
                          <a
                            className="link-button"
                            href={websiteHref}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            Visit Website
                          </a>
                        )}
                        {phoneHref && (
                          <a className="link-button" href={phoneHref}>
                            Call
                          </a>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="result-actions">
                    <button onClick={() => handleAnalyze(result)} disabled={Boolean(isAnalyzingThis)}>
                      {isAnalyzingThis ? 'Analyzing...' : 'Analyze Supplier'}
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </section>

        {assessment && (
          <section className="card assessment-card">
            <div className="assessment-header">
              <div>
                <p className="label">Selected supplier</p>
                <h3>{assessment.business?.name}</h3>
                <p className="muted">{formatAddress(assessment.business || {})}</p>
              </div>
              <div className={`score-pill ${riskAccent(assessment.risk_score)}`}>
                <span>Risk score</span>
                <strong>{assessment.risk_score}</strong>
              </div>
            </div>

            <div className="info-grid">
              <div className="info-block">
                <p className="label">Azure snapshot</p>
                <p className="info-title">{assessment.business?.name || 'Not available'}</p>
                <p className="muted">{formatAddress(assessment.business || {})}</p>
                {(assessedWebsiteHref || assessedPhoneHref) && (
                  <div className="contact-links">
                    {assessedWebsiteHref && (
                      <a className="link-button" href={assessedWebsiteHref} target="_blank" rel="noopener noreferrer">
                        Visit Website
                      </a>
                    )}
                    {assessedPhoneHref && (
                      <a className="link-button" href={assessedPhoneHref}>
                        Call
                      </a>
                    )}
                  </div>
                )}
              </div>
              <div className="info-block">
                <p className="label">GLEIF snapshot</p>
                {gleifSummary ? (
                  <div className="gleif-summary">
                    <p>
                      <strong>LEI:</strong> {gleifSummary.lei || 'Not available'}
                    </p>
                    <p>
                      <strong>Registration status:</strong> {gleifSummary.registration_status || 'Unknown'}
                    </p>
                    <p>
                      <strong>Entity status:</strong> {gleifSummary.entity_status || 'Unknown'}
                    </p>
                    <p>
                      <strong>Jurisdiction:</strong> {gleifSummary.legal_jurisdiction || 'Not available'}
                    </p>
                    <p>
                      <strong>Legal address:</strong> {formatGleifAddress(gleifSummary)}
                    </p>
                  </div>
                ) : (
                  <p className="muted">No matching GLEIF record was returned.</p>
                )}
              </div>
            </div>

            <div className="summary-block">
              <p className="label">AI summary</p>
              <p className="explanation">{assessment.explanation}</p>
            </div>

            <div className="risk-sections">
              <FinancialHealthPanel
                loading={deepRiskLoading}
                error={deepRiskError}
                data={deepRisk?.financial_health}
              />
              <ComplianceLegalPanel
                loading={deepRiskLoading}
                error={deepRiskError}
                data={deepRisk?.compliance_legal}
              />
              <OperationalResiliencePanel
                loading={deepRiskLoading}
                error={deepRiskError}
                data={deepRisk?.operational_resilience}
              />
              <EsgReputationPanel
                loading={deepRiskLoading}
                error={deepRiskError}
                data={deepRisk?.esg_reputation}
              />
            </div>

            {assessmentFactors.length > 0 && (
              <div className="factors">
                {assessmentFactors.map(([key, value]) => (
                  <div key={key}>
                    <span className="label">{key}</span>
                    <p>{typeof value === 'boolean' ? (value ? 'Yes' : 'No') : value ?? 'Not available'}</p>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        <section className="card">
          <h3>Debug</h3>
          <div className="debug-section">
            <h4>Azure</h4>
            <DebugPanel title="Search Raw Response" data={azureRaw} />
            <DebugPanel title="Selected Azure Result" data={assessment?.azure_raw} />
          </div>
          <div className="debug-section">
            <h4>GLEIF Enrichment</h4>
            <DebugPanel title="GLEIF Request" data={assessment?.gleif_request} />
            <DebugPanel title="GLEIF Raw Response" data={assessment?.gleif_raw} />
          </div>
          <DebugPanel title="Risk Debug Payload" data={assessment?.risk_debug_payload} />
        </section>
      </main>
    </div>
  )
}

export default App
