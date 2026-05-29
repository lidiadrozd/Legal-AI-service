import { useCallback, useEffect, useRef, useState } from 'react';
import { speechApi } from '@/api/speech';
import { getApiErrorMessage } from '@/utils/apiError';

const MAX_RECORD_MS = 60_000;

function pickMimeType(): string {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/ogg',
  ];
  for (const type of candidates) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(type)) {
      return type;
    }
  }
  return 'audio/webm';
}

function extensionForMime(mime: string): string {
  if (mime.includes('ogg')) return 'recording.ogg';
  return 'recording.webm';
}

export function useVoiceInput() {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const mimeTypeRef = useRef('audio/webm');
  const stopTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cleanupStream = useCallback(() => {
    if (stopTimerRef.current) {
      clearTimeout(stopTimerRef.current);
      stopTimerRef.current = null;
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    mediaRecorderRef.current = null;
  }, []);

  useEffect(() => () => cleanupStream(), [cleanupStream]);

  const stopRecording = useCallback((): Promise<Blob | null> => {
    return new Promise((resolve) => {
      const recorder = mediaRecorderRef.current;
      if (!recorder || recorder.state === 'inactive') {
        cleanupStream();
        setIsRecording(false);
        resolve(null);
        return;
      }

      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeTypeRef.current });
        chunksRef.current = [];
        cleanupStream();
        setIsRecording(false);
        resolve(blob.size > 0 ? blob : null);
      };

      try {
        recorder.stop();
      } catch {
        cleanupStream();
        setIsRecording(false);
        resolve(null);
      }
    });
  }, [cleanupStream]);

  const startRecording = useCallback(async () => {
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Браузер не поддерживает запись с микрофона');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      mimeTypeRef.current = pickMimeType();
      chunksRef.current = [];

      const recorder = new MediaRecorder(stream, { mimeType: mimeTypeRef.current });
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.start(250);
      setIsRecording(true);

      stopTimerRef.current = setTimeout(() => {
        void stopRecording();
      }, MAX_RECORD_MS);
    } catch {
      cleanupStream();
      setError('Нет доступа к микрофону. Разрешите использование в настройках браузера.');
    }
  }, [cleanupStream, stopRecording]);

  const toggleRecording = useCallback(async (): Promise<string | null> => {
    if (isTranscribing) return null;

    if (isRecording) {
      const blob = await stopRecording();
      if (!blob) {
        setError('Запись пустая');
        return null;
      }

      try {
        setIsTranscribing(true);
        const res = await speechApi.transcribe(blob, extensionForMime(mimeTypeRef.current));
        return res.text.trim() || null;
      } catch (err) {
        setError(getApiErrorMessage(err, 'Не удалось распознать речь'));
        return null;
      } finally {
        setIsTranscribing(false);
      }
    }

    await startRecording();
    return null;
  }, [isRecording, isTranscribing, startRecording, stopRecording]);

  const isSupported =
    typeof window !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== 'undefined';

  return {
    isSupported,
    isRecording,
    isTranscribing,
    isBusy: isRecording || isTranscribing,
    error,
    clearError: () => setError(null),
    toggleRecording,
    cancelRecording: async () => {
      if (isRecording) {
        chunksRef.current = [];
        await stopRecording();
      }
    },
  };
}
