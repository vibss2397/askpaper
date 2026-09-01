/// <reference types="@raycast/api">

/* 🚧 🚧 🚧
 * This file is auto-generated from the extension's manifest.
 * Do not modify manually. Instead, update the `package.json` file.
 * 🚧 🚧 🚧 */

/* eslint-disable @typescript-eslint/ban-types */

type ExtensionPreferences = {
  /** Daemon URL - URL of the paper-agent daemon (e.g. http://localhost:8765) */
  "daemonUrl": string,
  /** Default Space - Fallback space if no context or previous space is available */
  "defaultSpace": string
}

/** Preferences accessible in all the extension's commands */
declare type Preferences = ExtensionPreferences

declare namespace Preferences {
  /** Preferences accessible in the `capture-and-ask` command */
  export type CaptureAndAsk = ExtensionPreferences & {}
  /** Preferences accessible in the `ask` command */
  export type Ask = ExtensionPreferences & {}
  /** Preferences accessible in the `session-history` command */
  export type SessionHistory = ExtensionPreferences & {}
  /** Preferences accessible in the `end-paper` command */
  export type EndPaper = ExtensionPreferences & {}
}

declare namespace Arguments {
  /** Arguments passed to the `capture-and-ask` command */
  export type CaptureAndAsk = {}
  /** Arguments passed to the `ask` command */
  export type Ask = {}
  /** Arguments passed to the `session-history` command */
  export type SessionHistory = {}
  /** Arguments passed to the `end-paper` command */
  export type EndPaper = {}
}

