/**
 * Create / edit dialog for an approval matrix.
 *
 * The matrix is edited as one document — basics, conditions and approval levels
 * together — because that is how the backend stores it: a save replaces the whole
 * rule set and level set. Editing them separately would imply a partial save that
 * the API does not offer.
 *
 * `code` is locked in edit mode: it identifies the matrix in configuration and
 * renaming it would orphan any reference to it.
 */

import { useEffect } from 'react';

import { zodResolver } from '@hookform/resolvers/zod';
import { Button } from 'primereact/button';
import { Dialog } from 'primereact/dialog';
import { Divider } from 'primereact/divider';
import { Dropdown } from 'primereact/dropdown';
import { InputNumber } from 'primereact/inputnumber';
import { InputSwitch } from 'primereact/inputswitch';
import { InputText } from 'primereact/inputtext';
import { Message } from 'primereact/message';
import { Tag } from 'primereact/tag';
import { Controller, useFieldArray, useForm } from 'react-hook-form';
import { z } from 'zod';

import { useRoles } from '@features/user-management/hooks/useRoles';
import { useUsers } from '@features/user-management/hooks/useUsers';

import {
  ASSIGNMENT_TYPES,
  RULE_DATA_TYPES,
  RULE_OPERATORS,
  type ApprovalMatrix,
  type CreateApprovalMatrixRequest,
} from '../models/ApprovalMatrix';

const OPERATOR_LABELS: Record<(typeof RULE_OPERATORS)[number], string> = {
  EQ: 'equals',
  NEQ: 'does not equal',
  GT: 'is greater than',
  GTE: 'is at least',
  LT: 'is less than',
  LTE: 'is at most',
  IN: 'is one of',
  NOT_IN: 'is none of',
  CONTAINS: 'contains',
  STARTS_WITH: 'starts with',
};

const operatorOptions = RULE_OPERATORS.map((value) => ({
  label: OPERATOR_LABELS[value],
  value,
}));

const dataTypeOptions = RULE_DATA_TYPES.map((value) => ({
  label: value.charAt(0) + value.slice(1).toLowerCase(),
  value,
}));

const assignmentTypeOptions = ASSIGNMENT_TYPES.map((value) => ({
  label: value === 'ROLE' ? 'Role' : 'User',
  value,
}));

const ruleSchema = z.object({
  field: z.string().min(1, 'Field is required').max(100),
  operator: z.enum(RULE_OPERATORS),
  value: z.string().min(1, 'Value is required').max(500),
  data_type: z.enum(RULE_DATA_TYPES),
  logical_group: z.string().min(1).max(50),
});

const assignmentSchema = z
  .object({
    level: z.number().int().min(1).max(99),
    assignment_type: z.enum(ASSIGNMENT_TYPES),
    user_id: z.string().nullable(),
    role_id: z.string().nullable(),
  })
  .refine((value) => value.assignment_type !== 'ROLE' || Boolean(value.role_id), {
    message: 'Select a role',
    path: ['role_id'],
  })
  .refine((value) => value.assignment_type !== 'USER' || Boolean(value.user_id), {
    message: 'Select a user',
    path: ['user_id'],
  });

const matrixSchema = z.object({
  code: z
    .string()
    .min(2, 'Code must be at least 2 characters')
    .max(100)
    .regex(/^[A-Z0-9_]+$/, 'Use upper case letters, numbers and underscores only'),
  name: z.string().min(2, 'Name must be at least 2 characters').max(255),
  entity_type: z
    .string()
    .min(2, 'Entity type must be at least 2 characters')
    .max(100)
    .regex(/^[a-z0-9_]+$/, 'Use lower case letters, numbers and underscores only'),
  priority: z.number().int().min(0).max(999),
  is_active: z.boolean(),
  rules: z.array(ruleSchema),
  assignments: z.array(assignmentSchema),
});

type MatrixFormData = z.infer<typeof matrixSchema>;

const EMPTY: MatrixFormData = {
  code: '',
  name: '',
  entity_type: '',
  priority: 0,
  is_active: true,
  rules: [],
  assignments: [],
};

interface ApprovalMatrixFormProps {
  visible: boolean;
  matrix?: ApprovalMatrix | null;
  loading?: boolean;
  onHide: () => void;
  onSubmit: (data: CreateApprovalMatrixRequest) => void;
}

export const ApprovalMatrixForm = ({
  visible,
  matrix,
  loading,
  onHide,
  onSubmit,
}: ApprovalMatrixFormProps) => {
  const isEdit = Boolean(matrix);
  const { roleOptions, loading: rolesLoading } = useRoles();
  const { data: usersData, isLoading: usersLoading } = useUsers(0, 500);

  const userOptions = (usersData?.users ?? []).map((user) => ({
    label: user.employee_name ? `${user.username} — ${user.employee_name}` : user.username,
    value: user.id,
  }));

  const {
    register,
    handleSubmit,
    control,
    reset,
    watch,
    formState: { errors },
  } = useForm<MatrixFormData>({
    resolver: zodResolver(matrixSchema),
    defaultValues: EMPTY,
  });

  const rules = useFieldArray({ control, name: 'rules' });
  const assignments = useFieldArray({ control, name: 'assignments' });

  useEffect(() => {
    if (!visible) return;
    reset(
      matrix
        ? {
            code: matrix.code,
            name: matrix.name,
            entity_type: matrix.entity_type,
            priority: matrix.priority,
            is_active: matrix.is_active,
            rules: matrix.rules.map((rule) => ({
              field: rule.field,
              operator: rule.operator,
              value: rule.value,
              data_type: rule.data_type,
              logical_group: rule.logical_group,
            })),
            assignments: matrix.assignments.map((assignment) => ({
              level: assignment.level,
              assignment_type: assignment.assignment_type,
              user_id: assignment.user_id,
              role_id: assignment.role_id,
            })),
          }
        : EMPTY,
    );
  }, [visible, matrix, reset]);

  const close = () => {
    reset(EMPTY);
    onHide();
  };

  const nextLevel = () => {
    const levels = assignments.fields.map((_, index) => watch(`assignments.${index}.level`));
    return levels.length === 0 ? 1 : Math.max(...levels) + 1;
  };

  const footer = (
    <div className="flex justify-content-end gap-2">
      <Button label="Cancel" icon="pi pi-times" severity="secondary" outlined onClick={close} />
      <Button
        label={isEdit ? 'Save Changes' : 'Create'}
        icon="pi pi-check"
        loading={loading}
        onClick={handleSubmit(onSubmit)}
      />
    </div>
  );

  return (
    <Dialog
      header={isEdit ? `Edit Matrix — ${matrix?.code}` : 'New Approval Matrix'}
      visible={visible}
      onHide={close}
      style={{ width: '860px' }}
      breakpoints={{ '960px': '95vw' }}
      footer={footer}
      modal
      maximizable
      aria-label="Approval matrix dialog"
    >
      <form className="flex flex-column gap-4 pt-3">
        {/* Basics */}
        <div className="grid">
          <div className="col-12 md:col-6 flex flex-column gap-2">
            <label htmlFor="am-code" className="font-medium">
              Code
            </label>
            <InputText
              id="am-code"
              {...register('code')}
              placeholder="e.g. FILING_BY_AMOUNT"
              disabled={isEdit}
              className={errors.code ? 'p-invalid' : ''}
            />
            {errors.code && <small className="p-error">{errors.code.message}</small>}
          </div>

          <div className="col-12 md:col-6 flex flex-column gap-2">
            <label htmlFor="am-name" className="font-medium">
              Name
            </label>
            <InputText
              id="am-name"
              {...register('name')}
              placeholder="e.g. Filing approval by amount"
              className={errors.name ? 'p-invalid' : ''}
            />
            {errors.name && <small className="p-error">{errors.name.message}</small>}
          </div>

          <div className="col-12 md:col-6 flex flex-column gap-2">
            <label htmlFor="am-entity-type" className="font-medium">
              Entity Type
            </label>
            <InputText
              id="am-entity-type"
              {...register('entity_type')}
              placeholder="e.g. compliance_task"
              className={errors.entity_type ? 'p-invalid' : ''}
            />
            {errors.entity_type && <small className="p-error">{errors.entity_type.message}</small>}
          </div>

          <div className="col-12 md:col-3 flex flex-column gap-2">
            <label htmlFor="am-priority" className="font-medium">
              Priority
            </label>
            <Controller
              name="priority"
              control={control}
              render={({ field }) => (
                <InputNumber
                  id="am-priority"
                  value={field.value}
                  onValueChange={(e) => field.onChange(e.value ?? 0)}
                  min={0}
                  max={999}
                  showButtons
                  aria-label="Matrix priority"
                />
              )}
            />
            <small className="text-600">Lowest matching wins</small>
          </div>

          <div className="col-12 md:col-3 flex flex-column gap-2">
            <label htmlFor="am-is-active" className="font-medium">
              Active
            </label>
            <Controller
              name="is_active"
              control={control}
              render={({ field }) => (
                <InputSwitch
                  id="am-is-active"
                  checked={field.value}
                  onChange={(e) => field.onChange(e.value)}
                  aria-label="Matrix active"
                />
              )}
            />
          </div>
        </div>

        <Divider className="my-0" />

        {/* Conditions */}
        <div>
          <div className="flex align-items-center justify-content-between mb-2">
            <div>
              <span className="font-semibold">Conditions</span>
              <p className="text-600 text-sm mt-1 mb-0">
                Conditions in the same group must all match; separate groups are alternatives.
              </p>
            </div>
            <Button
              label="Add Condition"
              icon="pi pi-plus"
              size="small"
              outlined
              onClick={() =>
                rules.append({
                  field: '',
                  operator: 'EQ',
                  value: '',
                  data_type: 'STRING',
                  logical_group: 'default',
                })
              }
            />
          </div>

          {rules.fields.length === 0 ? (
            <Message
              severity="info"
              text="No conditions — this matrix will match every record of its entity type."
            />
          ) : (
            <div className="flex flex-column gap-2">
              {rules.fields.map((row, index) => (
                <div key={row.id} className="grid align-items-start">
                  <div className="col-12 md:col-3">
                    <InputText
                      {...register(`rules.${index}.field`)}
                      placeholder="Field, e.g. amount"
                      className={`w-full ${errors.rules?.[index]?.field ? 'p-invalid' : ''}`}
                      aria-label={`Condition ${index + 1} field`}
                    />
                    {errors.rules?.[index]?.field && (
                      <small className="p-error">{errors.rules[index]?.field?.message}</small>
                    )}
                  </div>
                  <div className="col-12 md:col-3">
                    <Controller
                      name={`rules.${index}.operator`}
                      control={control}
                      render={({ field }) => (
                        <Dropdown
                          value={field.value}
                          options={operatorOptions}
                          onChange={(e) => field.onChange(e.value)}
                          className="w-full"
                          aria-label={`Condition ${index + 1} operator`}
                        />
                      )}
                    />
                  </div>
                  <div className="col-12 md:col-2">
                    <InputText
                      {...register(`rules.${index}.value`)}
                      placeholder="Value"
                      className={`w-full ${errors.rules?.[index]?.value ? 'p-invalid' : ''}`}
                      aria-label={`Condition ${index + 1} value`}
                    />
                    {errors.rules?.[index]?.value && (
                      <small className="p-error">{errors.rules[index]?.value?.message}</small>
                    )}
                  </div>
                  <div className="col-12 md:col-2">
                    <Controller
                      name={`rules.${index}.data_type`}
                      control={control}
                      render={({ field }) => (
                        <Dropdown
                          value={field.value}
                          options={dataTypeOptions}
                          onChange={(e) => field.onChange(e.value)}
                          className="w-full"
                          aria-label={`Condition ${index + 1} data type`}
                        />
                      )}
                    />
                  </div>
                  <div className="col-8 md:col-1">
                    <InputText
                      {...register(`rules.${index}.logical_group`)}
                      placeholder="Group"
                      className="w-full"
                      aria-label={`Condition ${index + 1} group`}
                    />
                  </div>
                  <div className="col-4 md:col-1 flex justify-content-end">
                    <Button
                      icon="pi pi-trash"
                      rounded
                      outlined
                      severity="danger"
                      size="small"
                      onClick={() => rules.remove(index)}
                      aria-label={`Remove condition ${index + 1}`}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <Divider className="my-0" />

        {/* Approval levels */}
        <div>
          <div className="flex align-items-center justify-content-between mb-2">
            <div>
              <span className="font-semibold">Approval Levels</span>
              <p className="text-600 text-sm mt-1 mb-0">
                Approvers are asked in ascending level order.
              </p>
            </div>
            <Button
              label="Add Level"
              icon="pi pi-plus"
              size="small"
              outlined
              onClick={() =>
                assignments.append({
                  level: nextLevel(),
                  assignment_type: 'ROLE',
                  user_id: null,
                  role_id: null,
                })
              }
            />
          </div>

          {assignments.fields.length === 0 ? (
            <Message severity="warn" text="No approval levels defined yet." />
          ) : (
            <div className="flex flex-column gap-2">
              {assignments.fields.map((row, index) => {
                const type = watch(`assignments.${index}.assignment_type`);
                const rowErrors = errors.assignments?.[index];
                return (
                  <div key={row.id} className="grid align-items-start">
                    <div className="col-3 md:col-2">
                      <Controller
                        name={`assignments.${index}.level`}
                        control={control}
                        render={({ field }) => (
                          <InputNumber
                            value={field.value}
                            onValueChange={(e) => field.onChange(e.value ?? 1)}
                            min={1}
                            max={99}
                            className="w-full"
                            aria-label={`Level number for row ${index + 1}`}
                          />
                        )}
                      />
                    </div>
                    <div className="col-9 md:col-3">
                      <Controller
                        name={`assignments.${index}.assignment_type`}
                        control={control}
                        render={({ field }) => (
                          <Dropdown
                            value={field.value}
                            options={assignmentTypeOptions}
                            onChange={(e) => {
                              // Clear the other target so a switched row cannot
                              // submit a role id under a USER assignment.
                              field.onChange(e.value);
                              assignments.update(index, {
                                level: watch(`assignments.${index}.level`),
                                assignment_type: e.value,
                                user_id: null,
                                role_id: null,
                              });
                            }}
                            className="w-full"
                            aria-label={`Assignment type for row ${index + 1}`}
                          />
                        )}
                      />
                    </div>
                    <div className="col-10 md:col-6">
                      {type === 'ROLE' ? (
                        <Controller
                          name={`assignments.${index}.role_id`}
                          control={control}
                          render={({ field }) => (
                            <Dropdown
                              value={field.value}
                              options={roleOptions}
                              onChange={(e) => field.onChange(e.value)}
                              placeholder={rolesLoading ? 'Loading roles...' : 'Select a role'}
                              disabled={rolesLoading}
                              filter
                              className={`w-full ${rowErrors?.role_id ? 'p-invalid' : ''}`}
                              aria-label={`Role for level row ${index + 1}`}
                            />
                          )}
                        />
                      ) : (
                        <Controller
                          name={`assignments.${index}.user_id`}
                          control={control}
                          render={({ field }) => (
                            <Dropdown
                              value={field.value}
                              options={userOptions}
                              onChange={(e) => field.onChange(e.value)}
                              placeholder={usersLoading ? 'Loading users...' : 'Select a user'}
                              disabled={usersLoading}
                              filter
                              className={`w-full ${rowErrors?.user_id ? 'p-invalid' : ''}`}
                              aria-label={`User for level row ${index + 1}`}
                            />
                          )}
                        />
                      )}
                      {rowErrors?.role_id && (
                        <small className="p-error">{rowErrors.role_id.message}</small>
                      )}
                      {rowErrors?.user_id && (
                        <small className="p-error">{rowErrors.user_id.message}</small>
                      )}
                    </div>
                    <div className="col-2 md:col-1 flex justify-content-end">
                      <Button
                        icon="pi pi-trash"
                        rounded
                        outlined
                        severity="danger"
                        size="small"
                        onClick={() => assignments.remove(index)}
                        aria-label={`Remove level row ${index + 1}`}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {isEdit && (
          <Message
            severity="info"
            text="Saving replaces the stored conditions and levels with what is shown here."
          />
        )}

        {assignments.fields.length > 0 && (
          <div className="flex align-items-center gap-2 flex-wrap">
            <span className="text-600 text-sm">Chain:</span>
            {[...new Set(assignments.fields.map((_, i) => watch(`assignments.${i}.level`)))]
              .sort((a, b) => a - b)
              .map((level) => (
                <Tag key={level} value={`L${level}`} severity="info" />
              ))}
          </div>
        )}
      </form>
    </Dialog>
  );
};
