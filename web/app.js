/**
 * Voice Assistant QA Platform - Web UI JavaScript
 * Plain vanilla JS, no frameworks, stable data-testid attributes for testing
 */

(function() {
    'use strict';

    // Configuration
    const API_BASE = '/';
    const API_KEY = 'test-api-key-change-in-production'; // In production, load from secure config

    // DOM Elements
    const elements = {
        recordBtn: document.getElementById('record-btn'),
        stopBtn: document.getElementById('stop-btn'),
        transcript: document.getElementById('transcript'),
        chatHistory: document.getElementById('chat-history'),
        statusIndicator: document.querySelector('[data-testid="status-indicator"]'),
        statusText: document.querySelector('[data-testid="status-text"]'),
        errorBanner: document.querySelector('[data-testid="error-banner"]'),
        waveformCanvas: document.getElementById('waveform-canvas'),
    };

    // State
    let mediaRecorder = null;
    let audioChunks = [];
    let audioContext = null;
    let analyser = null;
    let animationId = null;
    let sessionId = generateSessionId();
    let isRecording = false;

    // Initialize
    function init() {
        bindEvents();
        updateStatus('ready', 'Ready');
        checkMicrophonePermission();
    }

    function bindEvents() {
        elements.recordBtn.addEventListener('click', startRecording);
        elements.stopBtn.addEventListener('click', stopRecording);
    }

    function generateSessionId() {
        return 'sess_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    function updateStatus(state, text) {
        elements.statusIndicator.className = 'status-indicator ' + state;
        elements.statusText.textContent = text;
    }

    function showError(message) {
        elements.errorBanner.textContent = message;
        elements.errorBanner.classList.add('visible');
        setTimeout(() => {
            elements.errorBanner.classList.remove('visible');
        }, 8000);
    }

    function hideError() {
        elements.errorBanner.classList.remove('visible');
    }

    async function checkMicrophonePermission() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            stream.getTracks().forEach(track => track.stop());
            elements.recordBtn.disabled = false;
        } catch (err) {
            if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
                elements.recordBtn.disabled = true;
                showError('Microphone access denied. Please enable microphone permissions in your browser settings and refresh.');
            } else {
                showError('Microphone error: ' + err.message);
            }
        }
    }

    async function startRecording() {
        hideError();

        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                    sampleRate: 16000,
                }
            });

            audioChunks = [];
            mediaRecorder = new MediaRecorder(stream, {
                mimeType: 'audio/webm;codecs=opus'
            });

            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    audioChunks.push(event.data);
                }
            };

            mediaRecorder.onstop = () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                sendAudio(audioBlob);
                stream.getTracks().forEach(track => track.stop());
            };

            mediaRecorder.start(100); // Collect data every 100ms
            isRecording = true;
            updateUIForRecording(true);
            startVisualizer(stream);

        } catch (err) {
            if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
                showError('Microphone access denied. Please check browser permissions.');
            } else {
                showError('Recording failed: ' + err.message);
            }
            updateUIForRecording(false);
        }
    }

    function stopRecording() {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
        }
        stopVisualizer();
        isRecording = false;
        updateUIForRecording(false);
    }

    function updateUIForRecording(recording) {
        elements.recordBtn.style.display = recording ? 'none' : 'inline-flex';
        elements.stopBtn.style.display = recording ? 'inline-flex' : 'none';
        elements.recordBtn.disabled = recording;
        elements.stopBtn.disabled = !recording;
    }

    function startVisualizer(stream) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        analyser = audioContext.createAnalyser();
        analyser.fftSize = 256;

        const source = audioContext.createMediaStreamSource(stream);
        source.connect(analyser);

        const canvas = elements.waveformCanvas;
        const ctx = canvas.getContext('2d');
        const bufferLength = analyser.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);

        canvas.width = canvas.offsetWidth;
        canvas.height = canvas.offsetHeight;

        function draw() {
            animationId = requestAnimationFrame(draw);
            analyser.getByteFrequencyData(dataArray);

            ctx.fillStyle = '#f1f5f9';
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            const barWidth = (canvas.width / bufferLength) * 2.5;
            let x = 0;

            for (let i = 0; i < bufferLength; i++) {
                const barHeight = (dataArray[i] / 255) * canvas.height * 0.8;
                const hue = 220 + (dataArray[i] / 255) * 30;
                ctx.fillStyle = `hsl(${hue}, 70%, 50%)`;
                ctx.fillRect(x, canvas.height - barHeight, barWidth, barHeight);
                x += barWidth + 1;
            }
        }

        draw();
    }

    function stopVisualizer() {
        if (animationId) {
            cancelAnimationFrame(animationId);
            animationId = null;
        }
        if (audioContext) {
            audioContext.close();
            audioContext = null;
        }
        const ctx = elements.waveformCanvas.getContext('2d');
        ctx.clearRect(0, 0, elements.waveformCanvas.width, elements.waveformCanvas.height);
    }

    async function sendAudio(audioBlob) {
        updateStatus('processing', 'Processing...');

        const formData = new FormData();
        formData.append('audio_file', audioBlob, 'recording.webm');
        formData.append('session_id', sessionId);

        try {
            const response = await fetch(API_BASE + 'audio/chat', {
                method: 'POST',
                headers: {
                    'X-API-Key': API_KEY,
                },
                body: formData,
            });

            if (!response.ok) {
                const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
                throw new Error(error.detail || `HTTP ${response.status}`);
            }

            const data = await response.json();
            handleResponse(data);

        } catch (err) {
            console.error('API error:', err);
            if (err.name === 'TypeError' && err.message.includes('fetch')) {
                showError('Network error. Is the server running?');
            } else {
                showError('Error: ' + err.message);
            }
            updateStatus('error', 'Error');
            setTimeout(() => updateStatus('ready', 'Ready'), 3000);
        }
    }

    function handleResponse(data) {
        // Update transcript
        elements.transcript.value = data.transcript || '(no transcript)';

        // Add user message
        if (data.transcript) {
            addMessage('user', data.transcript);
        }

        // Add assistant message
        addMessage('bot', data.reply, data.audio_reply_url);

        // Update status
        updateStatus('ready', 'Ready');
    }

    function addMessage(role, text, audioUrl = null) {
        const welcomeMsg = elements.chatHistory.querySelector('[data-testid="welcome-message"]');
        if (welcomeMsg) {
            welcomeMsg.remove();
        }

        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message ' + role;
        messageDiv.setAttribute('data-testid', role === 'user' ? 'user-message' : 'bot-message');

        const avatar = document.createElement('div');
        avatar.className = 'message-avatar ' + role;
        avatar.setAttribute('aria-hidden', 'true');
        avatar.textContent = role === 'bot' ? '🤖' : '👤';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        const senderDiv = document.createElement('div');
        senderDiv.className = 'message-sender';
        senderDiv.setAttribute('data-testid', role === 'user' ? 'user-sender' : 'bot-sender');
        senderDiv.textContent = role === 'bot' ? 'Assistant' : 'You';

        const textDiv = document.createElement('div');
        textDiv.className = 'message-text';
        textDiv.setAttribute('data-testid', role === 'user' ? 'user-text' : 'bot-text');
        textDiv.textContent = text;

        contentDiv.appendChild(senderDiv);
        contentDiv.appendChild(textDiv);

        if (audioUrl && role === 'bot') {
            const audioEl = document.createElement('audio');
            audioEl.className = 'message-audio';
            audioEl.controls = true;
            audioEl.src = audioUrl;
            audioEl.setAttribute('data-testid', 'bot-audio');
            contentDiv.appendChild(audioEl);
        }

        if (role === 'user') {
            messageDiv.appendChild(contentDiv);
            messageDiv.appendChild(avatar);
        } else {
            messageDiv.appendChild(avatar);
            messageDiv.appendChild(contentDiv);
        }

        elements.chatHistory.appendChild(messageDiv);
        elements.chatHistory.scrollTop = elements.chatHistory.scrollHeight;
    }

    // Handle page unload
    window.addEventListener('beforeunload', () => {
        if (mediaRecorder && mediaRecorder.state === 'recording') {
            mediaRecorder.stop();
        }
        stopVisualizer();
    });

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();