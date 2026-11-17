import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { EmployeeADServicePage } from '@features/service-menu/pages/EmployeeADServicePage';

import { server } from '../../mocks/server';
import { renderWithProviders, screen, waitFor, within } from '../../test-utils';

const BASE = '/api/v1/services/employee-ad';

const reachable = {
  service: 'Employee AD (Darwin)',
  configured: true,
  base_url: 'https://ad.example.test',
  status: 'reachable',
  status_code: 200,
  url: 'https://ad.example.test/health',
};

beforeEach(() => {
  server.use(http.get(`${BASE}/health`, () => HttpResponse.json(reachable)));
});

/** The card that contains the given title, so assertions stay inside one section. */
const cardWithTitle = (title: string): HTMLElement => {
  const card = screen.getByText(title).closest('.p-card');
  if (!card) throw new Error(`no card titled ${title}`);
  return card as HTMLElement;
};

describe('EmployeeADServicePage — service health', () => {
  it('shows a spinner while the health check is in flight', async () => {
    server.use(
      http.get(`${BASE}/health`, async () => {
        await new Promise((resolve) => setTimeout(resolve, 100));
        return HttpResponse.json(reachable);
      }),
    );

    renderWithProviders(<EmployeeADServicePage />);

    expect(screen.getByText('Checking service status...')).toBeInTheDocument();
    await screen.findByText('https://ad.example.test');
    expect(screen.queryByText('Checking service status...')).not.toBeInTheDocument();
  });

  it('reports a reachable, configured service as Online with its details', async () => {
    renderWithProviders(<EmployeeADServicePage />);

    expect(await screen.findByText('Online')).toBeInTheDocument();
    expect(screen.getByText('Employee AD (Darwin)')).toBeInTheDocument();
    expect(screen.getByText('reachable').closest('.p-tag')).toHaveClass('p-tag-success');
    expect(screen.getByText('Yes').closest('.p-tag')).toHaveClass('p-tag-success');
    expect(screen.getByText('https://ad.example.test')).toBeInTheDocument();
    expect(screen.getByText('HTTP Code:')).toBeInTheDocument();
    expect(screen.getByText('200')).toBeInTheDocument();
    expect(screen.queryByText('Error:')).not.toBeInTheDocument();
  });

  it('reports an unreachable service as Offline and shows its error', async () => {
    server.use(
      http.get(`${BASE}/health`, () =>
        HttpResponse.json({
          service: 'Employee AD (Darwin)',
          configured: false,
          base_url: 'https://ad.example.test',
          status: 'unreachable',
          url: 'https://ad.example.test/health',
          error: 'connect ECONNREFUSED',
        }),
      ),
    );

    renderWithProviders(<EmployeeADServicePage />);

    // Wait on the loaded report: the header badge reads "Offline" while still loading too.
    expect(await screen.findByText('connect ECONNREFUSED')).toBeInTheDocument();
    expect(screen.getByText('Offline')).toBeInTheDocument();
    expect(screen.getByText('unreachable').closest('.p-tag')).toHaveClass('p-tag-danger');
    expect(screen.getByText('No').closest('.p-tag')).toHaveClass('p-tag-warning');
    expect(screen.queryByText('HTTP Code:')).not.toBeInTheDocument();
  });

  it('falls back to Offline / unknown when the health endpoint itself fails', async () => {
    server.use(
      http.get(`${BASE}/health`, () => HttpResponse.json({ detail: 'down' }, { status: 500 })),
    );

    renderWithProviders(<EmployeeADServicePage />);

    // The hook retries once (about a second) before settling on the error.
    expect(await screen.findByText('unknown', undefined, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByText('Offline')).toBeInTheDocument();
    expect(screen.getByText('Employee AD (Darwin)')).toBeInTheDocument();
  });

  it('re-checks the service when Refresh health is clicked', async () => {
    const user = userEvent.setup();
    let calls = 0;
    server.use(
      http.get(`${BASE}/health`, () => {
        calls += 1;
        return HttpResponse.json(
          calls === 1
            ? reachable
            : { ...reachable, status: 'unreachable', status_code: undefined, error: 'timeout' },
        );
      }),
    );
    renderWithProviders(<EmployeeADServicePage />);
    expect(await screen.findByText('Online')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Refresh health' }));

    expect(await screen.findByText('Offline')).toBeInTheDocument();
    expect(calls).toBe(2);
  });
});

describe('EmployeeADServicePage — validate credentials', () => {
  it('warns and sends nothing when the employee id is blank', async () => {
    const user = userEvent.setup();
    let posted = false;
    server.use(
      http.post(`${BASE}/validate-credentials`, () => {
        posted = true;
        return HttpResponse.json({});
      }),
    );
    renderWithProviders(<EmployeeADServicePage />);
    await screen.findByText('Online');

    await user.click(screen.getByRole('button', { name: 'Validate' }));

    expect(await screen.findByText('Employee ID is required')).toBeInTheDocument();
    expect(posted).toBe(false);
  });

  it('treats a whitespace-only employee id as blank', async () => {
    const user = userEvent.setup();
    renderWithProviders(<EmployeeADServicePage />);
    await screen.findByText('Online');

    await user.type(screen.getByLabelText('Employee ID'), '   ');
    await user.click(screen.getByRole('button', { name: 'Validate' }));

    expect(await screen.findByText('Employee ID is required')).toBeInTheDocument();
  });

  it('posts the trimmed id and password, then shows a valid result', async () => {
    const user = userEvent.setup();
    let body: unknown = null;
    server.use(
      http.post(`${BASE}/validate-credentials`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          is_success: true,
          is_valid_user: true,
          raw_response: { IsSuccess: true, IsValidUser: true },
        });
      }),
    );
    renderWithProviders(<EmployeeADServicePage />);
    await screen.findByText('Online');

    await user.type(screen.getByLabelText('Employee ID'), '  93300040 ');
    await user.type(screen.getByPlaceholderText('Enter password'), 'secret-pass');
    await user.click(screen.getByRole('button', { name: 'Validate' }));

    const card = cardWithTitle('POST /validatecredentials');
    expect(await within(card).findByText('Valid User')).toBeInTheDocument();
    expect(body).toEqual({ employee_id: '93300040', password: 'secret-pass' });
    expect(within(card).getByText('Valid User').closest('.p-tag')).toHaveClass('p-tag-success');
    expect(within(card).getByText('Success').closest('.p-tag')).toHaveClass('p-tag-success');
    expect(card.querySelector('pre')).toHaveTextContent('"IsValidUser": true');
    expect(await screen.findByText(/is valid$/)).toBeInTheDocument();
  });

  it('shows an invalid result, with a warning toast, when AD rejects the credentials', async () => {
    const user = userEvent.setup();
    server.use(
      http.post(`${BASE}/validate-credentials`, () =>
        HttpResponse.json({
          is_success: true,
          is_valid_user: false,
          raw_response: { IsValidUser: false },
        }),
      ),
    );
    renderWithProviders(<EmployeeADServicePage />);
    await screen.findByText('Online');

    await user.type(screen.getByLabelText('Employee ID'), '93300040');
    await user.type(screen.getByPlaceholderText('Enter password'), 'wrong');
    await user.click(screen.getByRole('button', { name: 'Validate' }));

    const card = cardWithTitle('POST /validatecredentials');
    expect(await within(card).findByText('Invalid User')).toBeInTheDocument();
    expect(within(card).getByText('Invalid User').closest('.p-tag')).toHaveClass('p-tag-danger');
    expect(await screen.findByText('Employee 93300040 validation failed')).toBeInTheDocument();
  });

  it('toasts the backend message when the call fails', async () => {
    const user = userEvent.setup();
    server.use(
      http.post(`${BASE}/validate-credentials`, () =>
        HttpResponse.json({ detail: 'AD service unavailable' }, { status: 502 }),
      ),
    );
    renderWithProviders(<EmployeeADServicePage />);
    await screen.findByText('Online');

    await user.type(screen.getByLabelText('Employee ID'), '93300040');
    await user.type(screen.getByPlaceholderText('Enter password'), 'x');
    await user.click(screen.getByRole('button', { name: 'Validate' }));

    expect(await screen.findByText('AD service unavailable')).toBeInTheDocument();
  });
});

describe('EmployeeADServicePage — fetch selected employees', () => {
  it('warns and sends nothing when no ids are entered', async () => {
    const user = userEvent.setup();
    let posted = false;
    server.use(
      http.post(`${BASE}/selected-employees`, () => {
        posted = true;
        return HttpResponse.json({});
      }),
    );
    renderWithProviders(<EmployeeADServicePage />);
    await screen.findByText('Online');

    await user.click(screen.getByRole('button', { name: 'Fetch Selected' }));

    expect(await screen.findByText('Enter at least one Employee ID')).toBeInTheDocument();
    expect(posted).toBe(false);
  });

  it('splits the comma-separated ids, trims them and drops blanks', async () => {
    const user = userEvent.setup();
    let body: unknown = null;
    server.use(
      http.post(`${BASE}/selected-employees`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ employees: [{ id: '1001' }] });
      }),
    );
    renderWithProviders(<EmployeeADServicePage />);
    await screen.findByText('Online');

    await user.type(screen.getByLabelText('Employee IDs'), '1001, 1002 ,, 1003 ,');
    await user.click(screen.getByRole('button', { name: 'Fetch Selected' }));

    expect(await screen.findByText('Selected employees fetched')).toBeInTheDocument();
    expect(body).toEqual({ employee_ids: ['1001', '1002', '1003'] });
  });

  it('renders the JSON response with a 200 OK tag', async () => {
    const user = userEvent.setup();
    server.use(
      http.post(`${BASE}/selected-employees`, () =>
        HttpResponse.json({ employees: [{ id: '1001', name: 'Asha' }] }),
      ),
    );
    renderWithProviders(<EmployeeADServicePage />);
    await screen.findByText('Online');
    const card = cardWithTitle('POST /getselectedemployees');
    expect(within(card).queryByText('200 OK')).not.toBeInTheDocument();

    await user.type(screen.getByLabelText('Employee IDs'), '1001');
    await user.click(screen.getByRole('button', { name: 'Fetch Selected' }));

    expect(await within(card).findByText('200 OK')).toBeInTheDocument();
    expect(card.querySelector('pre')).toHaveTextContent('"name": "Asha"');
  });

  it('toasts the backend message when the call fails', async () => {
    const user = userEvent.setup();
    server.use(
      http.post(`${BASE}/selected-employees`, () =>
        HttpResponse.json({ detail: 'Bad ids' }, { status: 400 }),
      ),
    );
    renderWithProviders(<EmployeeADServicePage />);
    await screen.findByText('Online');

    await user.type(screen.getByLabelText('Employee IDs'), 'zzz');
    await user.click(screen.getByRole('button', { name: 'Fetch Selected' }));

    expect(await screen.findByText('Bad ids')).toBeInTheDocument();
  });
});

describe('EmployeeADServicePage — all employees and hierarchy', () => {
  it('fetches all employees and renders the response', async () => {
    const user = userEvent.setup();
    server.use(
      http.get(`${BASE}/employees`, () => HttpResponse.json({ employees: [{ id: 'A1' }] })),
    );
    renderWithProviders(<EmployeeADServicePage />);
    await screen.findByText('Online');
    const card = cardWithTitle('GET /getemployees');

    await user.click(screen.getByRole('button', { name: 'Get All Employees' }));

    expect(await screen.findByText('All employees fetched')).toBeInTheDocument();
    expect(card.querySelector('pre')).toHaveTextContent('"id": "A1"');
  });

  it('toasts the backend message when fetching all employees fails', async () => {
    const user = userEvent.setup();
    server.use(
      http.get(`${BASE}/employees`, () =>
        HttpResponse.json({ message: 'Upstream timed out' }, { status: 504 }),
      ),
    );
    renderWithProviders(<EmployeeADServicePage />);
    await screen.findByText('Online');

    await user.click(screen.getByRole('button', { name: 'Get All Employees' }));

    expect(await screen.findByText('Upstream timed out')).toBeInTheDocument();
  });

  it('fetches the hierarchy and renders the response', async () => {
    const user = userEvent.setup();
    server.use(http.get(`${BASE}/hierarchy`, () => HttpResponse.json({ root: 'CEO' })));
    renderWithProviders(<EmployeeADServicePage />);
    await screen.findByText('Online');
    const card = cardWithTitle('GET /getHierarchyData');

    await user.click(screen.getByRole('button', { name: 'Get Hierarchy' }));

    expect(await screen.findByText('Hierarchy data fetched')).toBeInTheDocument();
    expect(card.querySelector('pre')).toHaveTextContent('"root": "CEO"');
  });

  it('toasts a fallback message when the hierarchy call fails without a body', async () => {
    const user = userEvent.setup();
    server.use(http.get(`${BASE}/hierarchy`, () => new HttpResponse(null, { status: 500 })));
    renderWithProviders(<EmployeeADServicePage />);
    await screen.findByText('Online');

    await user.click(screen.getByRole('button', { name: 'Get Hierarchy' }));

    await waitFor(() => expect(screen.getByText('Failed to fetch')).toBeInTheDocument());
  });
});
