/**
 * Container Master page.
 * Uses the reusable SimpleMaster component (single-field master).
 */

import { SimpleMaster } from '@features/masters/components/SimpleMaster';

export const ContainerMasterPage = () => (
  <SimpleMaster
    title="Container"
    fieldLabel="Container Type"
    fieldKey="container_type"
    apiPath="containers"
  />
);
