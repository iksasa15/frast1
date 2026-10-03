import { BrowserRouter, Routes, Route } from 'react-router';
import { Shell } from '@/components/layout/Shell';
import { OperationsPage } from '@/pages/OperationsPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { AuditPage } from '@/pages/AuditPage';
import { DevicesPage } from '@/pages/DevicesPage';
import { IncidentsPage } from '@/pages/IncidentsPage';
import { AnalyticsPage } from '@/pages/AnalyticsPage';
import { AgentsPage } from '@/pages/AgentsPage';
import {
  ServicesPage,
} from '@/pages/Placeholders';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<OperationsPage />} />
          <Route path="incidents" element={<IncidentsPage />} />
          <Route path="incidents/:id" element={<IncidentsPage />} />
          <Route path="devices" element={<DevicesPage />} />
          <Route path="services" element={<ServicesPage />} />
          <Route path="agents" element={<AgentsPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="audit" element={<AuditPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
