const express = require("express");
const multer = require("multer");
const path = require("path");
const {
  uploadDocument,
  getDocuments,
  deleteDocument,
} = require("../../controllers/documentController");
const { protect } = require("../../middleware/auth");

const router = express.Router();

const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, path.join(__dirname, "../../uploads"));
  },
  filename: (req, file, cb) => {
    const unique = Date.now() + "-" + Math.round(Math.random() * 1e9);
    cb(null, unique + path.extname(file.originalname));
  },
});

const upload = multer({
  storage,
  limits: { fileSize: 20 * 1024 * 1024 }, // 20 MB
  fileFilter: (req, file, cb) => {
    const allowed = /pdf|txt|md|docx|doc/;
    const ext = allowed.test(path.extname(file.originalname).toLowerCase());
    const mime = allowed.test(file.mimetype) || file.mimetype.includes("document") || file.mimetype.includes("text");
    if (ext || mime) {
      cb(null, true);
    } else {
      cb(new Error("Only PDF, TXT, MD, DOCX files are allowed"));
    }
  },
});

router.use(protect);

router.post("/upload", upload.single("file"), uploadDocument);
router.get("/", getDocuments);
router.delete("/:id", deleteDocument);

module.exports = router;
