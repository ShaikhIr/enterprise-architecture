/**
 * Dosage Master page.
 * Thin wrapper passing config to the reusable SimpleMaster component.
 */

import { SimpleMaster } from '../components/SimpleMaster';

export const DosageMasterPage = () => (
  <SimpleMaster
    title="Dosage"
    fieldLabel="Dosage"
    fieldKey="dosage"
    apiPath="dosages"
  />
);
