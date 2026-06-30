/**
 * Mode of Shipment Master page.
 * Thin wrapper passing config to the reusable SimpleMaster component.
 */

import { SimpleMaster } from '../components/SimpleMaster';

export const ModeOfShipmentMasterPage = () => (
  <SimpleMaster
    title="Mode of Shipment"
    fieldLabel="Mode Name"
    fieldKey="mode_name"
    apiPath="modes-of-shipment"
  />
);
