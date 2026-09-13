const http = require('http');

const server = http.createServer((req, res) => {
  console.log('Received request:');
  console.log('  Method:', req.method);
  console.log('  URL:', req.url);
  console.log('  Headers:', JSON.stringify(req.headers, null, 2));

  let body = '';
  req.on('data', chunk => {
    console.log('  Data chunk:', chunk);
    console.log('  Data chunk hex:', chunk.toString('hex'));
    console.log('  Data chunk as UTF-8:', chunk.toString('utf8'));
    body += chunk;
  });

  req.on('end', () => {
    console.log('  Full body:', body);
    console.log('  Full body length:', body.length);
    console.log('  Full body bytes:', Array.from(body).map(c => c.charCodeAt(0)));
    res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end(`Received: ${body}`);
  });

  req.on('error', err => {
    console.log('  Error:', err);
    res.writeHead(500);
    res.end('Server error');
  });
});

server.listen(3000, () => {
  console.log('Test server listening on port 3000');
});