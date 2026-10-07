/**
 * Canary - A free and open-source MMORPG server emulator
 * Copyright (©) 2019-2024 OpenTibiaBR <opentibiabr@outlook.com>
 * Repository: https://github.com/opentibiabr/canary
 * License: https://github.com/opentibiabr/canary/blob/main/LICENSE
 * Contributors: https://github.com/opentibiabr/canary/graphs/contributors
 * Website: https://docs.opentibiabr.com/
 */

#include <functional>
#include "pch.hpp"

#include "creatures/players/imbuements/imbuements.hpp"
#include "lua/global/globalevent.hpp"
#include "items/weapons/weapons.hpp"
#include "lua/creature/movement.hpp"
#include "lua/scripts/scripts.hpp"
#include "creatures/combat/spells.hpp"
#include "lua/callbacks/events_callbacks.hpp"

Scripts::Scripts() :
	scriptInterface("Scripts Interface") {
	scriptInterface.initState();
}

void Scripts::clearAllScripts() const {
	g_actions().clear();
	g_creatureEvents().clear();
	g_talkActions().clear();
	g_globalEvents().clear();
	g_spells().clear();
	g_moveEvents().clear();
	g_weapons().clear();
	g_callbacks().clear();
	g_monsters().clear();
}

bool Scripts::loadEventSchedulerScripts(const std::string &fileName) {
	auto coreFolder = g_configManager().getString(CORE_DIRECTORY, __FUNCTION__);
	const auto dir = std::filesystem::current_path() / coreFolder / "events" / "scripts" / "scheduler";
	if (!std::filesystem::exists(dir) || !std::filesystem::is_directory(dir)) {
		g_logger().warn("{} - Can not load folder 'scheduler' on {}/events/scripts'", __FUNCTION__, coreFolder);
		return false;
	}

	std::filesystem::recursive_directory_iterator endit;
	for (std::filesystem::recursive_directory_iterator it(dir); it != endit; ++it) {
		if (std::filesystem::is_regular_file(*it) && it->path().extension() == ".lua") {
			if (it->path().filename().string() == fileName) {
				if (scriptInterface.loadFile(it->path().string(), it->path().filename().string()) == -1) {
					g_logger().error(it->path().string());
					g_logger().error(scriptInterface.getLastLuaError());
					continue;
				}
				return true;
			}
		}
	}

	return false;
}

bool Scripts::loadScripts(std::string loadPath, bool isLib, bool reload) {
	const auto dir = std::filesystem::current_path() / loadPath;
	// Checks if the folder exists and is really a folder
	if (!std::filesystem::exists(dir) || !std::filesystem::is_directory(dir)) {
		g_logger().error("Can not load folder {}", loadPath);
		return false;
	}

	// Declare a string variable to store the last directory
	std::string lastDirectory;

	// std::filesystem::recursive_directory_iterator does not guarantee any
	// particular order, and can interleave a directory's own files with its
	// subdirectories' files. A script that defines a shared global (e.g.
	// lib/register_migrations.lua defining `Migration`) can land AFTER a
	// subfolder script that calls that global (e.g. lib/migrations/*.lua),
	// which then fails with "attempt to call global 'X' (a nil value)" --
	// nondeterministically, depending on filesystem entry order. Loading a
	// directory's own files (sorted) before recursing into its
	// subdirectories (sorted) makes load order deterministic and keeps
	// "helper file alongside the folder that uses it" working reliably.
	const std::function<void(const std::filesystem::path &)> loadDirectory = [&](const std::filesystem::path &currentDir) {
		std::vector<std::filesystem::path> files;
		std::vector<std::filesystem::path> subdirectories;
		for (const auto &entry : std::filesystem::directory_iterator(currentDir)) {
			if (entry.is_directory()) {
				subdirectories.push_back(entry.path());
			} else if (entry.is_regular_file()) {
				files.push_back(entry.path());
			}
		}
		std::sort(files.begin(), files.end());
		std::sort(subdirectories.begin(), subdirectories.end());

		for (const auto &realPath : files) {
			std::string fileFolder = realPath.parent_path().filename().string();
			// Script folder, example: "actions"
			std::string scriptFolder = realPath.parent_path().string();
			// Create a string_view for the fileFolder and scriptFolder strings
			std::string_view fileFolderView(fileFolder);
			std::string_view scriptFolderView(scriptFolder);
			// Filename, example: "demon.lua"
			std::string file(realPath.filename().string());
			if (realPath.extension() != ".lua") {
				// Skip this entry if it does not have a .lua extension
				continue;
			}

			// Check if file start with "#"
			if (std::string disable("#");
			    file.front() == disable.front()) {
				// Send log of disabled script
				if (g_configManager().getBoolean(SCRIPTS_CONSOLE_LOGS, __FUNCTION__)) {
					g_logger().info("[script]: {} [disabled]", realPath.filename().string());
				}
				// Skip for next loop and ignore disabled file
				continue;
			}

			// If the file is a library file or if the file's parent directory is not "lib" or "events"
			if (isLib || (fileFolderView != "lib" && fileFolderView != "events")) {
				// If console logs are enabled and the file is not a library file
				if (g_configManager().getBoolean(SCRIPTS_CONSOLE_LOGS, __FUNCTION__)) {
					// If the current directory is different from the last directory that was logged
					if (lastDirectory.empty() || lastDirectory != scriptFolderView) {
						// Update the last directory variable and log the directory name
						g_logger().info("Loading folder: [{}]", realPath.parent_path().filename().string());
					}
					lastDirectory = realPath.parent_path().string();
				}

				// If the function 'loadFile' returns -1, then there was an error loading the file
				if (scriptInterface.loadFile(realPath.string(), realPath.filename().string()) == -1) {
					// Log the error and the file path, and skip to the next iteration of the loop.
					g_logger().error(realPath.string());
					g_logger().error(scriptInterface.getLastLuaError());
					continue;
				}
			}

			if (g_configManager().getBoolean(SCRIPTS_CONSOLE_LOGS, __FUNCTION__)) {
				if (!reload) {
					g_logger().info("[script loaded]: {}", realPath.filename().string());
				} else {
					g_logger().info("[script reloaded]: {}", realPath.filename().string());
				}
			}
		}

		for (const auto &subdirectory : subdirectories) {
			loadDirectory(subdirectory);
		}
	};

	loadDirectory(dir);

	return true;
}
