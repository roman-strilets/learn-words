import { NavLink, Route, Routes } from 'react-router'

import { AddPhrasePage } from './pages/AddPhrasePage'
import { AddWordPage } from './pages/AddWordPage'
import { HomePage } from './pages/HomePage'
import { PhrasesPage } from './pages/PhrasesPage'
import { SettingsPage } from './pages/SettingsPage'
import { StatsPage } from './pages/StatsPage'
import { StudyPage } from './pages/StudyPage'
import { WordsPage } from './pages/WordsPage'

const NAV = [
  { to: '/', label: 'Главная', end: true },
  { to: '/study', label: 'Занятие', end: false },
  { to: '/words', label: 'Словарь', end: false },
  { to: '/phrases', label: 'Фразы', end: false },
  { to: '/stats', label: 'Статистика', end: false },
  { to: '/settings', label: 'Настройки', end: false },
]

export function App() {
  return (
    <div className="flex min-h-full flex-col">
      <nav className="border-b border-hairline">
        <ul className="mx-auto flex max-w-4xl gap-6 px-6 py-4">
          {NAV.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `text-sm transition-colors ${
                    isActive ? 'font-semibold text-accent' : 'text-muted hover:text-ink'
                  }`
                }
              >
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <main className="flex flex-1 flex-col items-center px-6 py-12">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/study" element={<StudyPage />} />
          <Route path="/words" element={<WordsPage />} />
          <Route path="/words/new" element={<AddWordPage />} />
          <Route path="/phrases" element={<PhrasesPage />} />
          <Route path="/phrases/new" element={<AddPhrasePage />} />
          <Route path="/stats" element={<StatsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route
            path="*"
            element={<p className="text-muted">Страница не найдена</p>}
          />
        </Routes>
      </main>
    </div>
  )
}
