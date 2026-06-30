/**
 * Therapeutic Category Master page.
 * Thin wrapper passing config to the reusable SimpleMaster component.
 */

import { SimpleMaster } from '../components/SimpleMaster';

export const TherapeuticCategoryMasterPage = () => (
  <SimpleMaster
    title="Therapeutic Category"
    fieldLabel="Therapeutic Category Name"
    fieldKey="therapeutic_category_name"
    apiPath="therapeutic-categories"
  />
);
