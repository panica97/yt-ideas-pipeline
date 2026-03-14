import { createBrowserRouter, Navigate } from 'react-router-dom';
import Layout from './components/layout/Layout';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import ChannelsPage from './pages/ChannelsPage';
import HistoryPage from './pages/HistoryPage';
import StrategiesPage from './pages/StrategiesPage';
import LivePage from './pages/LivePage';

function AuthGuard({ children }: { children: React.ReactNode }) {
  const apiKey = localStorage.getItem('irt_api_key');
  if (!apiKey) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/',
    element: (
      <AuthGuard>
        <Layout />
      </AuthGuard>
    ),
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'channels', element: <ChannelsPage /> },
      { path: 'history', element: <HistoryPage /> },
      { path: 'strategies', element: <StrategiesPage /> },
      { path: 'live', element: <LivePage /> },
    ],
  },
]);
