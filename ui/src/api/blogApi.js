import axios from "axios";

const API = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
});

export const generateBlog = async (topic) => {
  const res = await API.post("/generate", { topic });
  return res.data;
};