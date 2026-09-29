import { useEffect, useState } from 'react';

/** True while the browser reports no connection (window offline/online events). */
export default function useOnlineStatus() {
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    const goOffline = () => setOffline(true);
    const goOnline = () => setOffline(false);
    window.addEventListener('offline', goOffline);
    window.addEventListener('online', goOnline);
    return () => {
      window.removeEventListener('offline', goOffline);
      window.removeEventListener('online', goOnline);
    };
  }, []);
  return offline;
}
