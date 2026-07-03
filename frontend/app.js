const express = require('express');
const axios = require('axios');
const path = require('path');
const app = express();

const API_URL = process.env.API_URL || 'http://localhost:8000';
const PORT = process.env.PORT || 3000;

app.use(express.json());
app.use(express.static(path.join(__dirname, 'views')));

function handleApiError(err, res, action) {
  // Log the real reason for operators; never swallow it
  console.error(`API request failed (${action}):`, err.message);
  if (err.response) {
    // The API answered with an error status (e.g. 404, 503) — pass it through
    return res.status(err.response.status).json(err.response.data);
  }
  // The API never answered at all (down, unreachable)
  return res.status(502).json({ error: 'api unavailable' });
}

app.post('/submit', async (req, res) => {
  try {
    const response = await axios.post(`${API_URL}/jobs`);
    res.json(response.data);
  } catch (err) {
    handleApiError(err, res, 'create job');
  }
});

app.get('/status/:id', async (req, res) => {
  try {
    const response = await axios.get(`${API_URL}/jobs/${req.params.id}`);
    res.json(response.data);
  } catch (err) {
    handleApiError(err, res, 'get status');
  }
});

app.listen(PORT, () => {
  console.log(`Frontend running on port ${PORT}, API at ${API_URL}`);
});
