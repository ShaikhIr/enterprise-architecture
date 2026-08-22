import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { createMasterApi } from '@features/masters/api/createMasterApi';
import type { MasterListParams } from '@features/masters/models/common';

import { server } from '../../mocks/server';

interface Widget {
  id: string;
  code: string;
  name: string;
}

/**
 * All six real masters (`countryApi`, `stateApi`, ...) are one-line calls to
 * this factory with different type params and a different `basePath`/
 * `listKey`. Testing the factory once with a stand-in "widget" entity covers
 * the HTTP mechanics for every master; each master's own test file only
 * needs to check the one line that wires the factory up.
 */
const widgetApi = createMasterApi<
  Widget,
  { code: string; name: string },
  Partial<Widget>,
  MasterListParams
>('/masters/widgets', 'widgets');

describe('createMasterApi', () => {
  it('unwraps the dynamic envelope key into a normalised MasterPage', async () => {
    server.use(
      http.get('/api/v1/masters/widgets', () =>
        HttpResponse.json({
          widgets: [{ id: '1', code: 'W1', name: 'Widget One' }],
          total: 1,
          skip: 0,
          limit: 100,
        }),
      ),
    );

    const page = await widgetApi.list();

    expect(page).toEqual({
      items: [{ id: '1', code: 'W1', name: 'Widget One' }],
      total: 1,
      skip: 0,
      limit: 100,
    });
  });

  it('defaults to an empty items array when the envelope key is missing', async () => {
    server.use(
      http.get('/api/v1/masters/widgets', () =>
        HttpResponse.json({ total: 0, skip: 0, limit: 100 }),
      ),
    );

    const page = await widgetApi.list();

    expect(page.items).toEqual([]);
  });

  it('sends default pagination params, overridable by the caller', async () => {
    let captured: URL | undefined;
    server.use(
      http.get('/api/v1/masters/widgets', ({ request }) => {
        captured = new URL(request.url);
        return HttpResponse.json({ widgets: [], total: 0, skip: 0, limit: 100 });
      }),
    );

    await widgetApi.list({ skip: 20, limit: 10, search: 'foo' });

    expect(captured?.searchParams.get('skip')).toBe('20');
    expect(captured?.searchParams.get('limit')).toBe('10');
    expect(captured?.searchParams.get('search')).toBe('foo');
  });

  it('fetches a single record by id', async () => {
    server.use(
      http.get('/api/v1/masters/widgets/1', () =>
        HttpResponse.json({ id: '1', code: 'W1', name: 'Widget One' }),
      ),
    );

    const widget = await widgetApi.getById('1');

    expect(widget).toEqual({ id: '1', code: 'W1', name: 'Widget One' });
  });

  it('posts a create request and returns the created record', async () => {
    server.use(
      http.post('/api/v1/masters/widgets', async ({ request }) => {
        const body = await request.json();
        return HttpResponse.json({ id: '2', ...(body as object) }, { status: 201 });
      }),
    );

    const created = await widgetApi.create({ code: 'W2', name: 'Widget Two' });

    expect(created).toEqual({ id: '2', code: 'W2', name: 'Widget Two' });
  });

  it('patches an update request to the record path and returns the updated record', async () => {
    server.use(
      http.patch('/api/v1/masters/widgets/1', async ({ request }) => {
        const body = await request.json();
        return HttpResponse.json({ id: '1', code: 'W1', name: 'Widget One', ...(body as object) });
      }),
    );

    const updated = await widgetApi.update('1', { name: 'Renamed' });

    expect(updated.name).toBe('Renamed');
  });

  it('deletes a record by id', async () => {
    let deleteCalled = false;
    server.use(
      http.delete('/api/v1/masters/widgets/1', () => {
        deleteCalled = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    await widgetApi.remove('1');

    expect(deleteCalled).toBe(true);
  });

  it('propagates a 409 conflict from delete rather than swallowing it', async () => {
    server.use(
      http.delete('/api/v1/masters/widgets/1', () =>
        HttpResponse.json({ message: 'Widget is referenced elsewhere' }, { status: 409 }),
      ),
    );

    await expect(widgetApi.remove('1')).rejects.toMatchObject({ response: { status: 409 } });
  });
});
