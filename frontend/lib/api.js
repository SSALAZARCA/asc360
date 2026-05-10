export const getApiUrl = () => {
  const url = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
  return url.replace(/^http:\/\/(?!localhost)/, 'https://');
};
