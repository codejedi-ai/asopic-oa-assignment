/**
 * The page's HTML template structure, using JSX.
 */
import { Meta, Title, Links, Main, Scripts } from 'ice';
import { description } from '../package.json';

export default function Document() {
  return (
    <html>
      <head>
        <meta charSet="utf-8" />
        <meta name="description" content={description} />
        <link rel="icon" href="/favicon.ico" />
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet" />
        <script src="https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.4.0/p5.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/vanta/dist/vanta.topology.min.js"></script>
        <Meta />
        <Title />
        <Links />
      </head>
      <body>
        <Main />
        <Scripts />
      </body>
    </html>
  );
}
