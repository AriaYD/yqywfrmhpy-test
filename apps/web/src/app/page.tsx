import { redirect } from "next/navigation";

/** 根路径不承载内容——落到成长档案，那是学生每次进来最想先看的东西。 */
export default function Page() {
  redirect("/profile");
}
