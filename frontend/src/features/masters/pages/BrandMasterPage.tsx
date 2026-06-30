/**
 * Brand Master page.
 * Thin wrapper passing config to the reusable SimpleMaster component.
 */

import { SimpleMaster } from '../components/SimpleMaster';

export const BrandMasterPage = () => (
  <SimpleMaster
    title="Brand"
    fieldLabel="Brand Name"
    fieldKey="brand_name"
    apiPath="brands"
  />
);
