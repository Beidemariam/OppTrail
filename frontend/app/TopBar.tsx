"use client";

import { Link } from "react-router";

import type { User } from "../lib/domain";
import { useLogout } from "../lib/queries";
import { NotificationMenu } from "./NotificationMenu";

/** The signed-in header: where you are, what is waiting, and the way out. */
export function TopBar({ user }: { user: User }) {
  const logout = useLogout();

  return (
    <header className="topbar">
      <div>
        <p className="eyebrow">OppTrail</p>
        <h1>Opportunities</h1>
      </div>
      <div className="user-block">
        <Link className="secondary-button" to="/search">
          Search
        </Link>
        <NotificationMenu />
        <span>{user.name}</span>
        <button
          type="button"
          className="secondary-button"
          onClick={() => logout.mutate()}
        >
          Sign out
        </button>
      </div>
    </header>
  );
}
