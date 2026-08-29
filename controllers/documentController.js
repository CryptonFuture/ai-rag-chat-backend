const axios = require("axios");
const FormData = require("form-data");
const fs = require("fs");
const path = require("path");
const { v4: uuidv4 } = require("uuid");
const Document = require("../models/Document");

const PYTHON_RAG_URL = "https://python-rag-run.vercel.app/"

exports.uploadDocument = async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ success: false, message: "No file uploaded" });
    }

    const docId = uuidv4();
    const form = new FormData();
    form.append("file", fs.createReadStream(req.file.path), {
      filename: req.file.originalname,
      contentType: req.file.mimetype,
    });
    form.append("doc_id", docId);

    // Create DB record
    const doc = await Document.create({
      user: req.user._id,
      docId,
      filename: req.file.originalname,
      originalName: req.file.originalname,
      mimeType: req.file.mimetype,
      size: req.file.size,
      status: "processing",
    });

    try {
      const ragRes = await axios.post(`${PYTHON_RAG_URL}/ingest`, form, {
        headers: form.getHeaders(),
        timeout: 120000,
        maxContentLength: Infinity,
        maxBodyLength: Infinity,
      });

      doc.chunks = ragRes.data.chunks || 0;
      doc.status = "ready";
      await doc.save();

      // Cleanup temp file
      fs.unlink(req.file.path, () => {});

      res.status(201).json({
        success: true,
        document: doc,
        message: "Document uploaded and indexed successfully",
      });
    } catch (err) {
      doc.status = "failed";
      await doc.save();
      fs.unlink(req.file.path, () => {});
      console.error("Ingest error:", err.message);
      return res.status(500).json({
        success: false,
        message: `Failed to index document: ${err.message}`,
      });
    }
  } catch (error) {
    if (req.file) fs.unlink(req.file.path, () => {});
    res.status(500).json({ success: false, message: error.message });
  }
};

exports.getDocuments = async (req, res) => {
  try {
    const docs = await Document.find({ user: req.user._id }).sort({ createdAt: -1 });
    res.json({ success: true, documents: docs });
  } catch (error) {
    res.status(500).json({ success: false, message: error.message });
  }
};

exports.deleteDocument = async (req, res) => {
  try {
    const doc = await Document.findOne({ _id: req.params.id, user: req.user._id });
    if (!doc) {
      return res.status(404).json({ success: false, message: "Document not found" });
    }

    // Delete from Python RAG
    try {
      await axios.delete(`${PYTHON_RAG_URL}/documents/${doc.docId}`);
    } catch (err) {
      console.warn("Could not delete from RAG service:", err.message);
    }

    await doc.deleteOne();
    res.json({ success: true, message: "Document deleted" });
  } catch (error) {
    res.status(500).json({ success: false, message: error.message });
  }
};
