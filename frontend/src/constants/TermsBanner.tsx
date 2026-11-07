import React, { useState, useEffect } from 'react';
import { TERMS_PARAGRAPHS } from '../constants/site';

const TERMS_VERSION_KEY = 'legal_ai_accepted_terms_version';
const CURRENT_TERMS_VERSION = '1.1'; // Обнови версию, если соглашение изменилось

export const TermsBanner: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    const acceptedVersion = localStorage.getItem(TERMS_VERSION_KEY);
    if (acceptedVersion !== CURRENT_TERMS_VERSION) {
      setIsOpen(true);
    }
  }, []);

  const handleAccept = () => {
    localStorage.setItem(TERMS_VERSION_KEY, CURRENT_TERMS_VERSION);
    setIsOpen(false);
    setShowModal(false);
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Нижний баннер уведомления */}
      <div className="fixed bottom-0 left-0 right-0 z-50 bg-slate-900 text-white p-4 shadow-lg border-t border-slate-700 flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="text-sm max-w-4xl">
          <span className="font-semibold text-sky-400">Мы обновили Пользовательское соглашение.</span>{' '}
          В соответствии с изменениями рекомендуем вам ознакомиться с обновленными условиями использования сервиса «ИИ-Юрист».
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <button
            onClick={() => setShowModal(true)}
            className="px-4 py-2 text-sm font-medium text-slate-300 hover:text-white underline transition-colors"
          >
            Ознакомиться
          </button>
          <button
            onClick={handleAccept}
            className="px-5 py-2 text-sm font-medium bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors shadow"
          >
            Принять
          </button>
        </div>
      </div>

      {/* Модальное окно с полным текстом соглашения (при клике «Ознакомиться») */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="bg-white text-slate-900 rounded-xl max-w-2xl w-full max-h-[80vh] flex flex-col shadow-2xl">
            <div className="p-5 border-b border-slate-200 flex items-center justify-between">
              <h3 className="text-lg font-bold">Пользовательское соглашение</h3>
              <button
                onClick={() => setShowModal(false)}
                className="text-slate-400 hover:text-slate-600 text-xl font-bold px-2"
              >
                ✕
              </button>
            </div>
            <div className="p-6 overflow-y-auto space-y-3 text-sm text-slate-700">
              {TERMS_PARAGRAPHS.map((paragraph, index) => (
                <p key={index} className={paragraph.startsWith('1.') || paragraph.startsWith('2.') || paragraph.startsWith('5.') || paragraph.startsWith('8.') ? 'font-semibold mt-3' : ''}>
                  {paragraph}
                </p>
              ))}
            </div>
            <div className="p-4 border-t border-slate-200 flex justify-end gap-3 bg-slate-50 rounded-b-xl">
              <button
                onClick={() => setShowModal(false)}
                className="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-200 rounded-lg transition-colors"
              >
                Закрыть
              </button>
              <button
                onClick={handleAccept}
                className="px-5 py-2 text-sm font-medium bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors shadow"
              >
                Принять условия
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};