import { useCallback, useEffect, useRef, useState } from 'react';

type SpeechRecognitionCtor = new () => SpeechRecognition;

function getSpeechRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === 'undefined') return null;
  const w = window as Window & {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

interface UseSpeechToTextOptions {
  lang?: string;
  onFinalTranscript: (text: string) => void;
  onError?: (message: string) => void;
}

export function useSpeechToText({
  lang = 'ru-RU',
  onFinalTranscript,
  onError,
}: UseSpeechToTextOptions) {
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const onFinalRef = useRef(onFinalTranscript);
  const onErrorRef = useRef(onError);

  const isSupported = getSpeechRecognitionCtor() != null;

  useEffect(() => {
    onFinalRef.current = onFinalTranscript;
    onErrorRef.current = onError;
  }, [onFinalTranscript, onError]);

  const stop = useCallback(() => {
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    setIsListening(false);
  }, []);

  const start = useCallback(() => {
    const Ctor = getSpeechRecognitionCtor();
    if (!Ctor) {
      onErrorRef.current?.('Голосовой ввод не поддерживается в этом браузере');
      return;
    }

    stop();

    const recognition = new Ctor();
    recognition.lang = lang;
    recognition.continuous = true;
    recognition.interimResults = false;

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let chunk = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        if (event.results[i].isFinal) {
          chunk += event.results[i][0].transcript;
        }
      }
      const text = chunk.trim();
      if (text) onFinalRef.current(text);
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (event.error === 'aborted') return;
      const message =
        event.error === 'not-allowed'
          ? 'Нет доступа к микрофону'
          : event.error === 'no-speech'
            ? 'Речь не распознана'
            : 'Не удалось распознать речь';
      onErrorRef.current?.(message);
      stop();
    };

    recognition.onend = () => {
      recognitionRef.current = null;
      setIsListening(false);
    };

    recognitionRef.current = recognition;
    setIsListening(true);
    recognition.start();
  }, [lang, stop]);

  const toggle = useCallback(() => {
    if (isListening) stop();
    else start();
  }, [isListening, start, stop]);

  useEffect(() => () => stop(), [stop]);

  return { isSupported, isListening, start, stop, toggle };
}
