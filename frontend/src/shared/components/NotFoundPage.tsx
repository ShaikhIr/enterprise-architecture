/**
 * 404 page shown for unknown routes while the user is authenticated.
 * Renders inside the app shell so the user stays logged in — an unknown URL
 * must never bounce an authenticated user back to the login screen.
 */

import { Button } from 'primereact/button';
import { useNavigate } from 'react-router-dom';

export const NotFoundPage = () => {
  const navigate = useNavigate();

  return (
    <div className="flex align-items-center justify-content-center" style={{ minHeight: '60vh' }}>
      <div className="text-center">
        <h1 className="text-6xl font-bold mb-2" style={{ color: 'var(--color-primary)' }}>
          404
        </h1>
        <p className="mb-4 text-600">The page you're looking for doesn't exist.</p>
        <Button
          label="Back to Dashboard"
          icon="pi pi-home"
          onClick={() => navigate('/dashboard', { replace: true })}
        />
      </div>
    </div>
  );
};
