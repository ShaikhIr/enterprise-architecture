/**
 * EligibilityPanel — Read-only panel showing the 3-check claim validation triangle.
 * Displays: Agreement Valid, Mapping Valid, Status Valid, Overall Eligible.
 * Uses PrimeReact Tag and icons for pass/fail indicators.
 *
 * Requirements: 9.10, 9.11
 */

import { Dialog } from 'primereact/dialog';
import { Tag } from 'primereact/tag';
import { ProgressSpinner } from 'primereact/progressspinner';
import { useCheckEligibility } from '../hooks/useInvoices';

interface EligibilityPanelProps {
  invoiceId: string;
  visible: boolean;
  onHide: () => void;
}

interface CheckRowProps {
  label: string;
  valid: boolean;
  message: string;
}

const CheckRow = ({ label, valid, message }: CheckRowProps) => (
  <div className="flex align-items-center justify-content-between py-2 border-bottom-1 surface-border">
    <div className="flex align-items-center gap-2">
      <i
        className={`pi ${valid ? 'pi-check-circle text-green-500' : 'pi-times-circle text-red-500'}`}
        style={{ fontSize: '1.25rem' }}
      />
      <span className="font-medium">{label}</span>
    </div>
    <div className="flex align-items-center gap-2">
      <Tag
        value={valid ? 'Pass' : 'Fail'}
        severity={valid ? 'success' : 'danger'}
      />
      <small className="text-500 max-w-15rem text-right">{message}</small>
    </div>
  </div>
);

export const EligibilityPanel = ({ invoiceId, visible, onHide }: EligibilityPanelProps) => {
  const { data, isLoading, isError } = useCheckEligibility(invoiceId, visible && !!invoiceId);

  return (
    <Dialog
      header="Claim Eligibility Check"
      visible={visible}
      onHide={onHide}
      style={{ width: '550px' }}
      modal
      aria-label="Claim eligibility check panel"
    >
      <div className="flex flex-column gap-2 pt-2">
        {isLoading && (
          <div className="flex align-items-center justify-content-center py-4">
            <ProgressSpinner
              style={{ width: '40px', height: '40px' }}
              strokeWidth="4"
              aria-label="Loading eligibility check"
            />
            <span className="ml-3 text-600">Checking eligibility...</span>
          </div>
        )}

        {isError && (
          <div className="flex align-items-center gap-2 py-3">
            <i className="pi pi-exclamation-triangle text-orange-500 text-2xl" />
            <span className="text-600">Failed to load eligibility data. Please try again.</span>
          </div>
        )}

        {data && !isLoading && (
          <>
            <CheckRow
              label="Agreement Valid"
              valid={data.agreement_valid}
              message={data.agreement_message}
            />
            <CheckRow
              label="Mapping Valid"
              valid={data.mapping_valid}
              message={data.mapping_message}
            />
            <CheckRow
              label="Status Valid"
              valid={data.status_valid}
              message={data.status_message}
            />

            {/* Overall Eligibility */}
            <div className="flex align-items-center justify-content-center mt-3 pt-3 border-top-1 surface-border">
              <div className="flex align-items-center gap-3">
                <span className="font-bold text-lg">Overall Eligible:</span>
                <Tag
                  value={data.overall_eligible ? 'ELIGIBLE' : 'NOT ELIGIBLE'}
                  severity={data.overall_eligible ? 'success' : 'danger'}
                  className="text-lg px-3 py-1"
                />
              </div>
            </div>
          </>
        )}
      </div>
    </Dialog>
  );
};
