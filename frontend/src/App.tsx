import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { Send, FileImage, FileVideo, Download, Loader2, Bot, User } from 'lucide-react';

type Message = {
  id: string;
  sender: 'bot' | 'user';
  text?: string;
  isAction?: boolean;
  videoUrl?: string;
  timestamp: Date;
};

// Assuming the fastAPI backend runs locally on this port or uses an env variable in production
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "1",
      sender: "bot",
      text: "👋 Welcome to your Custom Watermark Platform!\n\nTo get started, please upload your transparent Logo (PNG) or Animation (WEBM/MOV).",
      timestamp: new Date()
    }
  ]);
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };
  useEffect(scrollToBottom, [messages]);

  const addMessage = (msg: Omit<Message, 'id' | 'timestamp'>) => {
    setMessages(prev => [...prev, { ...msg, id: Date.now().toString(), timestamp: new Date() }]);
  };

  const handleLogoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setLogoFile(file);
    addMessage({ sender: "user", text: `📎 Uploaded logo/animation: ${file.name}` });

    setTimeout(() => {
      addMessage({ sender: "bot", text: "Excellent! Now upload the Main Video you want to watermark." });
    }, 600);
  };

  const handleVideoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!logoFile) {
      alert("Please upload the logo first!");
      return;
    }

    setVideoFile(file);
    addMessage({ sender: "user", text: `🎬 Uploaded main video: ${file.name}` });

    setTimeout(() => {
      addMessage({ sender: "bot", text: "Great. I'm processing your video now. This might take a bit for larger files... ⏳" });
      processVideo(logoFile, file);
    }, 600);
  };

  const processVideo = async (logo: File, video: File) => {
    setIsProcessing(true);
    const formData = new FormData();
    formData.append('logo', logo);
    formData.append('video', video);

    try {
      const response = await axios.post(`${API_URL}/watermark`, formData, {
        responseType: 'blob', // Important for receiving the video file back
      });

      // Create a URL for the downloaded blob
      const url = window.URL.createObjectURL(new Blob([response.data]));

      addMessage({
        sender: "bot",
        text: "✅ Video processing fully complete! You can download your watermarked video below.",
        videoUrl: url
      });

    } catch (error) {
      console.error(error);
      addMessage({ sender: "bot", text: "❌ An error occurred during processing. Please try again or check the backend logs." });
    } finally {
      setIsProcessing(false);
      // Reset state for next conversion
      setLogoFile(null);
      setVideoFile(null);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50 text-gray-900 font-sans">

      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200 px-6 py-4 flex items-center justify-center">
        <h1 className="text-xl font-bold text-gray-800 flex items-center gap-2">
          <Bot className="text-blue-600" />
          Watermark Studio AI
        </h1>
      </header>

      {/* Chat Area */}
      <main className="flex-1 overflow-y-auto p-4 md:p-6 w-full max-w-4xl mx-auto flex flex-col gap-6">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex w-full ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`flex max-w-[85%] md:max-w-[70%] gap-3 ${msg.sender === 'user' ? 'flex-row-reverse' : 'flex-row'}`}>

              {/* Avatar */}
              <div className={`flex-shrink-0 h-8 w-8 rounded-full flex items-center justify-center 
                ${msg.sender === 'bot' ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-700'}`}>
                {msg.sender === 'bot' ? <Bot size={18} /> : <User size={18} />}
              </div>

              {/* Message Bubble */}
              <div className="flex flex-col gap-2">
                <div className={`
                  p-4 rounded-2xl whitespace-pre-wrap leading-relaxed shadow-sm text-[15px]
                  ${msg.sender === 'user'
                    ? 'bg-blue-600 text-white rounded-tr-sm'
                    : 'bg-white border border-gray-200 text-gray-800 rounded-tl-sm'
                  }
                `}>
                  {msg.text}
                </div>

                {/* Download Button if video attached */}
                {msg.videoUrl && (
                  <div className="mt-2 text-left">
                    <a
                      href={msg.videoUrl}
                      download="watermarked_video.mp4"
                      className="inline-flex items-center gap-2 bg-green-500 hover:bg-green-600 text-white px-5 py-2.5 rounded-lg shadow-sm transition-colors text-sm font-medium"
                    >
                      <Download size={18} />
                      Download Final Video
                    </a>
                  </div>
                )}
              </div>

            </div>
          </div>
        ))}
        {isProcessing && (
          <div className="flex w-full justify-start">
            <div className="flex max-w-[80%] gap-3 flex-row">
              <div className="flex-shrink-0 h-8 w-8 rounded-full bg-blue-600 text-white flex items-center justify-center">
                <Bot size={18} />
              </div>
              <div className="bg-white border border-gray-200 p-4 rounded-2xl rounded-tl-sm flex items-center gap-3 text-gray-600 text-[15px] shadow-sm">
                <Loader2 className="animate-spin text-blue-600" size={20} />
                Crunching pixels on the server...
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </main>

      {/* Input Area */}
      <footer className="bg-white border-t border-gray-200 p-4 w-full">
        <div className="max-w-4xl mx-auto flex items-center gap-3">

          <div className="flex-1 flex gap-3 bg-gray-100 p-2 rounded-xl relative">
            <input type="text" disabled placeholder="Interact using the upload buttons..." className="flex-1 bg-transparent px-3 outline-none text-gray-500 cursor-not-allowed hidden md:block" />

            {/* Upload Layout wrapper */}
            <div className="flex gap-2 w-full md:w-auto">
              <label className={`
                flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors shadow-sm cursor-pointer flex-1 md:flex-none
                ${!logoFile ? 'bg-blue-600 hover:bg-blue-700 text-white' : 'bg-gray-200 text-gray-500 cursor-not-allowed'}
               `}>
                <FileImage size={18} />
                <span>Upload Logo</span>
                <input
                  type="file"
                  className="hidden"
                  accept="image/png,video/quicktime,video/webm"
                  onChange={handleLogoUpload}
                  disabled={!!logoFile || isProcessing}
                />
              </label>

              <label className={`
                flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors shadow-sm cursor-pointer flex-1 md:flex-none
                ${logoFile && !videoFile && !isProcessing ? 'bg-blue-600 hover:bg-blue-700 text-white animate-pulse' : 'bg-gray-200 text-gray-500 cursor-not-allowed'}
               `}>
                <FileVideo size={18} />
                <span>Upload Video</span>
                <input
                  type="file"
                  className="hidden"
                  accept="video/*"
                  onChange={handleVideoUpload}
                  disabled={!logoFile || !!videoFile || isProcessing}
                />
              </label>
            </div>
          </div>

          <button disabled className="bg-blue-600 text-white p-3.5 rounded-xl opacity-50 cursor-not-allowed hidden sm:block">
            <Send size={20} className="-ml-1" />
          </button>

        </div>
      </footer>

    </div>
  );
}

export default App;
