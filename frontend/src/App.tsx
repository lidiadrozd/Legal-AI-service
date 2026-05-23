import { AppRouter } from './router';
import { CookieBanner } from '@/components/common/CookieBanner';

function App() {
  return (
    <>
      <AppRouter />
      <CookieBanner />
    </>
  );
}

export default App;
