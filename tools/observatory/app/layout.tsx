import './globals.css';
import ThemeToggle from './ThemeToggle';

export const metadata = { title: 'Observatory' };

// Applies a pinned theme before the first paint, so a dark page never flashes white.
const PRE_PAINT = `try{var t=localStorage.getItem('obs-theme');if(t==='light'||t==='dark')document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: PRE_PAINT }} /></head>
      <body>
        <ThemeToggle />
        {children}
      </body>
    </html>
  );
}
