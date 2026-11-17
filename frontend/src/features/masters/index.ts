// Masters feature barrel export

export { CountriesPage } from './pages/CountriesPage';
export { StatesPage } from './pages/StatesPage';
export { CategoriesOfLawPage } from './pages/CategoriesOfLawPage';
export { LegislationsPage } from './pages/LegislationsPage';
export { RulesPage } from './pages/RulesPage';
export { TaskTypesPage } from './pages/TaskTypesPage';

export { MasterCrudPage } from './components/MasterCrudPage';
export { MasterRowActions } from './components/MasterRowActions';
export { MasterStatusTag } from './components/MasterStatusTag';
export { CountryForm } from './components/CountryForm';
export { StateForm } from './components/StateForm';
export { CategoryOfLawForm } from './components/CategoryOfLawForm';
export { LegislationForm } from './components/LegislationForm';
export { RuleForm } from './components/RuleForm';
export { TaskTypeForm } from './components/TaskTypeForm';

export { countryApi } from './api/countryApi';
export { stateApi } from './api/stateApi';
export { categoryOfLawApi } from './api/categoryOfLawApi';
export { legislationApi } from './api/legislationApi';
export { ruleApi } from './api/ruleApi';
export { taskTypeApi } from './api/taskTypeApi';

export {
  useCountries,
  useCountryLookup,
  useCreateCountry,
  useUpdateCountry,
  useDeleteCountry,
} from './hooks/useCountries';
export {
  useStates,
  useStateLookup,
  useCreateState,
  useUpdateState,
  useDeleteState,
} from './hooks/useStates';
export {
  useCategoriesOfLaw,
  useCategoryOfLawLookup,
  useCreateCategoryOfLaw,
  useUpdateCategoryOfLaw,
  useDeleteCategoryOfLaw,
} from './hooks/useCategoriesOfLaw';
export {
  useLegislations,
  useLegislationLookup,
  useCreateLegislation,
  useUpdateLegislation,
  useDeleteLegislation,
} from './hooks/useLegislations';
export {
  useRules,
  useRuleLookup,
  useCreateRule,
  useUpdateRule,
  useDeleteRule,
} from './hooks/useRules';
export {
  useTaskTypes,
  useTaskTypeLookup,
  useCreateTaskType,
  useUpdateTaskType,
  useDeleteTaskType,
} from './hooks/useTaskTypes';
export { MASTER_KEYS } from './hooks/masterQueryKeys';

export { formatIsoDate, formatTimestampDate, fromIsoDate, toIsoDate } from './utils/isoDate';

export type { AuditedRecord, MasterRecord, MasterPage, MasterListParams } from './models/common';
/** What every `use*Lookup` returns: options for a dropdown plus a resolver for stored ids. */
export type { MasterLookup } from './hooks/useMasterLookup';
export type { Country, CreateCountryRequest, UpdateCountryRequest } from './models/Country';
export type { State, CreateStateRequest, UpdateStateRequest } from './models/State';
export type {
  CategoryOfLaw,
  CreateCategoryOfLawRequest,
  UpdateCategoryOfLawRequest,
} from './models/CategoryOfLaw';
export type {
  Legislation,
  CreateLegislationRequest,
  UpdateLegislationRequest,
} from './models/Legislation';
export type { Rule, CreateRuleRequest, UpdateRuleRequest } from './models/Rule';
export type { TaskType, CreateTaskTypeRequest, UpdateTaskTypeRequest } from './models/TaskType';
