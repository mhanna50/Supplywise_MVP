/**
 * @typedef {import('../types/deepRisk').DeepRiskResponse} DeepRiskResponse
 */

const detectApiOrigin = () => {
  const configuredOrigin = import.meta.env?.VITE_SUPPLIERS_API_ORIGIN?.trim();
  if (configuredOrigin) {
    return configuredOrigin.replace(/\/$/, '');
  }

  if (typeof window !== 'undefined' && window.location) {
    const { origin, port } = window.location;
    const devPorts = new Set(['5173', '4173']);
    if (port && devPorts.has(port)) {
      return 'http://localhost:8000';
    }
    return origin.replace(/\/$/, '');
  }

  return 'http://localhost:8000';
};

const BASE_URL = `${detectApiOrigin()}/api/suppliers`;

async function handleResponse(response) {
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || 'Request failed');
  }
  return response.json();
}

export async function searchSuppliers(query, filters = {}) {
  const params = new URLSearchParams();
  if (query) params.set('q', query);
  if (filters.city) params.set('city', filters.city);
  if (filters.state) params.set('state', filters.state);
  if (filters.country) params.set('country', filters.country);

  const response = await fetch(`${BASE_URL}/search/?${params.toString()}`);
  return handleResponse(response);
}

export async function assessSupplier(business) {
  const response = await fetch(`${BASE_URL}/assess/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(business),
  });
  return handleResponse(response);
}

/**
 * @param {Record<string, any>} business
 * @returns {Promise<DeepRiskResponse>}
 */
export async function runDeepRisk(business) {
  const response = await fetch(`${BASE_URL}/deep-risk/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(business),
  });
  return handleResponse(response);
}

export async function enrichSupplierWithGleif(business) {
  const response = await fetch(`${BASE_URL}/enrich/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(business),
  });
  return handleResponse(response);
}
