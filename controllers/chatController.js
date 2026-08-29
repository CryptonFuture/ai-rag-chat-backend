const axios = require("axios");
const Chat = require("../models/Chat");

const PYTHON_RAG_URL = process.env.PYTHON_RAG_URL

exports.getChats = async (req, res) => {
  try {
    const chats = await Chat.find({ user: req.user._id })
      .select("title createdAt updatedAt")
      .sort({ updatedAt: -1 });
    res.json({ success: true, chats });
  } catch (error) {
    res.status(500).json({ success: false, message: error.message });
  }
};

exports.getChat = async (req, res) => {
  try {
    const chat = await Chat.findOne({ _id: req.params.id, user: req.user._id });
    if (!chat) {
      return res.status(404).json({ success: false, message: "Chat not found" });
    }
    res.json({ success: true, chat });
  } catch (error) {
    res.status(500).json({ success: false, message: error.message });
  }
};

exports.createChat = async (req, res) => {
  try {
    const chat = await Chat.create({
      user: req.user._id,
      title: req.body.title || "New Chat",
      messages: [],
    });
    res.status(201).json({ success: true, chat });
  } catch (error) {
    res.status(500).json({ success: false, message: error.message });
  }
};

exports.deleteChat = async (req, res) => {
  try {
    const chat = await Chat.findOneAndDelete({ _id: req.params.id, user: req.user._id });
    if (!chat) {
      return res.status(404).json({ success: false, message: "Chat not found" });
    }
    res.json({ success: true, message: "Chat deleted" });
  } catch (error) {
    res.status(500).json({ success: false, message: error.message });
  }
};

exports.sendMessage = async (req, res) => {
  try {
    const { message, chatId } = req.body;
    if (!message || !message.trim()) {
      return res.status(400).json({ success: false, message: "Message is required" });
    }

    let chat;
    if (chatId) {
      chat = await Chat.findOne({ _id: chatId, user: req.user._id });
      if (!chat) {
        return res.status(404).json({ success: false, message: "Chat not found" });
      }
    } else {
      // Create new chat with first message as title
      const title = message.slice(0, 50) + (message.length > 50 ? "..." : "");
      chat = await Chat.create({
        user: req.user._id,
        title,
        messages: [],
      });
    }

    // Add user message
    chat.messages.push({ role: "user", content: message });

    // Call Python RAG service
    let answer = "Sorry, I could not process your request.";
    let sources = [];

    try {
      const history = chat.messages
        .slice(-6)
        .map((m) => ({ role: m.role, content: m.content }));

      const ragRes = await axios.post(
        `${PYTHON_RAG_URL}/query`,
        {
          question: message,
          top_k: 4,
          chat_history: history,
        },
        { timeout: 60000 }
      );

      answer = ragRes.data.answer;
      sources = ragRes.data.sources || [];
    } catch (err) {
      console.error("RAG service error:", err.message);
      answer =
        "⚠️ RAG service is unavailable. Please make sure the Python service is running on port 8000.\n\n" +
        `(Error: ${err.message})`;
    }

    // Add assistant message
    chat.messages.push({
      role: "assistant",
      content: answer,
      sources,
    });

    // Update title if it was still default and this is first real exchange
    if (chat.title === "New Chat" && chat.messages.length <= 2) {
      chat.title = message.slice(0, 50) + (message.length > 50 ? "..." : "");
    }

    await chat.save();

    res.json({
      success: true,
      chatId: chat._id,
      message: {
        role: "assistant",
        content: answer,
        sources,
      },
      chat,
    });
  } catch (error) {
    console.error(error);
    res.status(500).json({ success: false, message: error.message });
  }
};
