/**
 * Rule master screen.
 * Leaf of the hierarchy — the individual sections compliance tasks are raised against.
 */

import { useState } from 'react';

import { FilterMatchMode } from 'primereact/api';
import { Column } from 'primereact/column';
import type { DataTableFilterMeta } from 'primereact/datatable';
import { Dropdown } from 'primereact/dropdown';
import { Tag } from 'primereact/tag';

import { MasterCrudPage } from '../components/MasterCrudPage';
import { MasterRowActions } from '../components/MasterRowActions';
import { MasterStatusTag } from '../components/MasterStatusTag';
import { RuleForm } from '../components/RuleForm';
import { useCountryLookup } from '../hooks/useCountries';
import { useLegislationLookup } from '../hooks/useLegislations';
import { useMasterCrudController } from '../hooks/useMasterCrudController';
import { useMasterPermissions } from '../hooks/useMasterPermissions';
import { useCreateRule, useDeleteRule, useRules, useUpdateRule } from '../hooks/useRules';
import { useStateLookup } from '../hooks/useStates';
import type { CreateRuleRequest, Rule } from '../models/Rule';
import { formatIsoDate } from '../utils/isoDate';

const defaultFilters: DataTableFilterMeta = {
  code: { value: null, matchMode: FilterMatchMode.CONTAINS },
  name: { value: null, matchMode: FilterMatchMode.CONTAINS },
};

export const RulesPage = () => {
  const [filters, setFilters] = useState<DataTableFilterMeta>(defaultFilters);
  const [legislationId, setLegislationId] = useState<string | null>(null);
  const [countryId, setCountryId] = useState<string | null>(null);

  const countries = useCountryLookup();
  const states = useStateLookup();
  const legislations = useLegislationLookup();

  const { data, isLoading, refetch, isRefetching } = useRules({
    legislation_id: legislationId ?? undefined,
    country_id: countryId ?? undefined,
  });
  const createMutation = useCreateRule();
  const updateMutation = useUpdateRule();
  const deleteMutation = useDeleteRule();

  const permissions = useMasterPermissions('rules');

  const crud = useMasterCrudController<Rule, CreateRuleRequest>({
    entityLabel: 'Rule',
    labelOf: (row) => row.name,
    onCreate: (request) => createMutation.mutateAsync(request),
    onUpdate: (id, request) => updateMutation.mutateAsync({ id, request }),
    onDelete: (id) => deleteMutation.mutateAsync(id),
  });

  return (
    <MasterCrudPage<Rule>
      title="Rules"
      subtitle="Sections framed under a legislation"
      newLabel="New Rule"
      rows={data?.items ?? []}
      loading={isLoading}
      refreshing={isRefetching}
      onRefresh={() => refetch()}
      onNew={crud.openCreate}
      canCreate={permissions.canCreate}
      filters={filters}
      onFilterChange={setFilters}
      emptyMessage="No rules found."
      toastRef={crud.toast}
      toolbarEnd={
        <>
          <Dropdown
            value={countryId}
            options={countries.options}
            onChange={(e) => setCountryId(e.value ?? null)}
            placeholder="All countries"
            showClear
            filter
            className="w-12rem"
            aria-label="Filter by country"
          />
          <Dropdown
            value={legislationId}
            options={legislations.options}
            onChange={(e) => setLegislationId(e.value ?? null)}
            placeholder="All legislations"
            showClear
            filter
            className="w-14rem"
            aria-label="Filter by legislation"
          />
        </>
      }
      columns={
        <>
          <Column
            field="code"
            header="Code"
            sortable
            filter
            filterPlaceholder="Search..."
            style={{ width: '13rem' }}
          />
          <Column field="name" header="Name" sortable filter filterPlaceholder="Search..." />
          <Column
            header="Legislation"
            body={(row: Rule) => legislations.labelFor(row.legislation_id)}
          />
          <Column
            field="rule_number"
            header="Rule No."
            body={(row: Rule) => row.rule_number ?? '—'}
            style={{ width: '9rem' }}
          />
          <Column
            header="Scope"
            body={(row: Rule) =>
              row.state_id ? states.labelFor(row.state_id) : <Tag value="Central" severity="info" />
            }
          />
          <Column
            header="Effective"
            body={(row: Rule) => formatIsoDate(row.effective_date)}
            sortable
            field="effective_date"
            style={{ width: '9rem' }}
          />
          <Column
            header="Status"
            body={(row: Rule) => <MasterStatusTag isActive={row.is_active} />}
            style={{ width: '7rem' }}
          />
          {permissions.canModifyRows && (
            <Column
              header="Actions"
              body={(row: Rule) => (
                <MasterRowActions
                  label={row.name}
                  canUpdate={permissions.canUpdate}
                  canDelete={permissions.canDelete}
                  onEdit={() => crud.openEdit(row)}
                  onDelete={() => crud.requestDelete(row)}
                />
              )}
              style={{ width: '7rem' }}
            />
          )}
        </>
      }
    >
      <RuleForm
        visible={crud.dialogVisible}
        rule={crud.editing}
        saving={createMutation.isPending || updateMutation.isPending}
        onHide={crud.closeDialog}
        onSubmit={crud.submit}
      />
    </MasterCrudPage>
  );
};
