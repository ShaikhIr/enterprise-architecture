/**
 * Commission Slab Info Panel.
 * Read-only informational panel showing the commission calculation formula.
 * Displayed within the Agreement create and renewal dialogs.
 *
 * Requirements: 7.9
 */

import { Message } from 'primereact/message';

export const CommissionSlabInfo = () => {
  return (
    <div className="flex flex-column gap-2" aria-label="Commission slab formula">
      <Message
        severity="info"
        className="w-full justify-content-start"
        content={
          <div className="flex flex-column gap-1">
            <span className="font-semibold text-sm">Commission Slab Calculation</span>
            <span className="text-sm">
              Max Commission % reduced by Reduction % for each Slab in Days of payment delay
              past due date, floored at Min Commission %.
            </span>
          </div>
        }
      />
    </div>
  );
};
