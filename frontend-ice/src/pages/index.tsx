import { useEffect } from 'react';
import { useNavigate } from 'ice';

// The app's default landing route redirects to the Chat Assistant (mission) page.
export default function IndexPage() {
  const navigate = useNavigate();
  useEffect(() => {
    navigate('/mission', { replace: true });
  }, [navigate]);
  return null;
}
