/**
 * Шаблоны уведомлений для frontend
 * Используются для отображения в UI
 */

export const NOTIFICATION_TEMPLATES = {
    // Изменения законодательства
    LAW_CHANGE_STANDARD: {
      id: 'law_change_standard',
      title: 'Изменение законодательства: {category}',
      body: `Законодательство в сфере {category} изменилось.
  Это может повлиять на ваше дело: "{case_name}".
  
  📄 Изменение: {change_name}
  📅 Дата вступления: {date}
  
  Рекомендуем проверить актуальность документов.`,
      severity: 'medium',
      icon: '⚖️'
    },
  
    LAW_CHANGE_CRITICAL: {
      id: 'law_change_critical',
      title: '⚠️ ВНИМАНИЕ: Важное изменение закона',
      body: `ВНИМАНИЕ! Вступили в силу изменения, которые требуют немедленных действий.
  
  🚨 Дело: "{case_name}"
  ⏰ Срок для действий: {deadline}`,
      severity: 'high',
      icon: '🚨'
    },
  
    // Подача документов в суд
    COURT_FILING_SUCCESS: {
      id: 'court_filing_success',
      title: '✅ Документ успешно подан в суд',
      body: `Ваш документ "{document_name}" успешно отправлен.
  
  📮 Суд: {court_name}
  🔢 Номер отслеживания: {tracking_number}`,
      severity: 'medium',
      icon: '✅'
    },
  
    COURT_FILING_STATUS_CHANGED: {
      id: 'court_filing_status_changed',
      title: '📬 Статус подачи изменён: {new_status}',
      body: `Статус вашего документа изменён.
  
  📄 Документ: {document_name}
  ✅ Стало: {new_status}`,
      severity: 'medium',
      icon: '📬'
    },
  
    COURT_FILING_REJECTED: {
      id: 'court_filing_rejected',
      title: '❌ Документ отклонён судом',
      body: `К сожалению, суд отклонил ваш документ.
  
  📄 Документ: {document_name}
  Причина: {reason}`,
      severity: 'high',
      icon: '❌'
    },
  
    // Напоминания
    DEADLINE_REMINDER: {
      id: 'deadline_reminder',
      title: '⏰ Напоминание: Скоро дедлайн',
      body: `{user_name}, напоминаем о важном сроке!
  
  📄 Дело: "{case_name}"
  ⏳ Осталось дней: {days_remaining}`,
      severity: 'high',
      icon: '⏰'
    },
  
    PRETRIAL_DEADLINE_EXPIRED: {
      id: 'pretrial_deadline_expired',
      title: '⚠️ Истёк срок ответа на претензию',
      body: `Срок ответа на вашу претензию истёк.
  
  📮 Ответчик: {defendant_name}
  ✅ Статус: Ответ не получен`,
      severity: 'high',
      icon: '⚠️'
    },
  
    // Общие
    WELCOME_MESSAGE: {
      id: 'welcome_message',
      title: '👋 Добро пожаловать в ЮрAIст!',
      body: `{user_name}, рады приветствовать вас!
  
  Начать: {link}`,
      severity: 'low',
      icon: '👋'
    },
  
    SECURITY_ALERT: {
      id: 'security_alert',
      title: '🔐 Уведомление о безопасности',
      body: `Зафиксирован вход в ваш аккаунт.
  
  📱 Устройство: {device}
  🌍 Местоположение: {location}`,
      severity: 'critical',
      icon: '🔐'
    }
  };
  
  // Список всех шаблонов для удобного перебора
  export const ALL_NOTIFICATION_TYPES = Object.keys(NOTIFICATION_TEMPLATES);
  
  // Функция для получения шаблона по ID
  export const getNotificationTemplate = (templateId) => {
    if (!templateId) return null;
    return (
      NOTIFICATION_TEMPLATES[templateId] ||
      NOTIFICATION_TEMPLATES[String(templateId).toUpperCase()] ||
      null
    );
  };
  
  // Функция для форматирования текста с подстановкой переменных
  export const formatNotificationText = (template, variables) => {
    if (!template) return { title: '', body: '' };
    if (!variables || typeof variables !== 'object') {
      return { title: template.title, body: template.body };
    }

    let text = template.body;
    let title = template.title;
    
    Object.keys(variables).forEach(key => {
      const regex = new RegExp(`\\{${key}\\}`, 'g');
      text = text.replace(regex, variables[key]);
      title = title.replace(regex, variables[key]);
    });
    
    return { title, body: text };
  };
