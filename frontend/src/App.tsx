import React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppProvider } from './stores/AppContext';
import { MainLayout } from './layouts/MainLayout';
import { HomePage } from './pages/HomePage';
import { LoginPage, RegisterPage } from './pages/AuthPages';
import { ProblemsetPage } from './pages/ProblemsetPage';
import { ProblemDetailPage } from './pages/ProblemDetailPage';
import { SubmissionDetailPage, SubmissionsPage } from './pages/SubmissionsPage';
import { ContestDetailPage, ContestsPage } from './pages/ContestsPage';
import { ClassroomDetailPage, ClassroomsPage } from './pages/ClassroomsPage';
import { AdminDashboardPage } from './pages/AdminDashboardPage';
import { AdminProblemManagerPage } from './pages/AdminProblemManagerPage';

export const App: React.FC = () => {
  return (
    <AppProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<MainLayout />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/problems" element={<ProblemsetPage />} />
            <Route path="/problems/:codeOrId" element={<ProblemDetailPage />} />
            <Route path="/submissions" element={<SubmissionsPage />} />
            <Route path="/submissions/:id" element={<SubmissionDetailPage />} />
            <Route path="/contests" element={<ContestsPage />} />
            <Route path="/contests/:id" element={<ContestDetailPage />} />
            <Route path="/classrooms" element={<ClassroomsPage />} />
            <Route path="/classrooms/:id" element={<ClassroomDetailPage />} />
            <Route path="/admin" element={<AdminDashboardPage />} />
            <Route path="/admin/problems/new" element={<AdminProblemManagerPage />} />
            <Route path="/admin/problems/:id/edit" element={<AdminProblemManagerPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppProvider>
  );
};

export default App;
