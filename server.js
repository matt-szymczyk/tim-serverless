const express = require('express');
const path = require('path');
const app = express();

// Serve static files with correct MIME types
app.use(express.static('frontend', {
  setHeaders: (res, path) => {
    if (path.endsWith('.js')) {
      res.set('Content-Type', 'application/javascript; charset=utf-8');
    }
  }
}));

// Serve node_modules with correct MIME types
app.use('/node_modules', express.static('node_modules', {
  setHeaders: (res, path) => {
    if (path.endsWith('.js')) {
      res.set('Content-Type', 'application/javascript; charset=utf-8');
    }
  }
}));

app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'index.html'));
});

const PORT = 3003;
app.listen(PORT, () => {
  console.log(`Server running at http://localhost:${PORT}`);
});