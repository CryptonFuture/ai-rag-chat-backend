const express = require("express");
const {
  getChats,
  getChat,
  createChat,
  deleteChat,
  sendMessage,
} = require("../../controllers/chatController");
const { protect } = require("../middleware/auth");

const router = express.Router();

router.use(protect);

router.get("/", getChats);
router.post("/", createChat);
router.get("/:id", getChat);
router.delete("/:id", deleteChat);
router.post("/message", sendMessage);

module.exports = router;
