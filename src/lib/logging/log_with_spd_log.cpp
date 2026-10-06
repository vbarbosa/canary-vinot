/**
 * Canary - A free and open-source MMORPG server emulator
 * Copyright (©) 2019-2024 OpenTibiaBR <opentibiabr@outlook.com>
 * Repository: https://github.com/opentibiabr/canary
 * License: https://github.com/opentibiabr/canary/blob/main/LICENSE
 * Contributors: https://github.com/opentibiabr/canary/graphs/contributors
 * Website: https://docs.opentibiabr.com/
 */
#include <spdlog/spdlog.h>

#include "pch.hpp"
#include "lib/di/container.hpp"

LogWithSpdLog::LogWithSpdLog() {
	setLevel("info");
	spdlog::set_pattern("[%Y-%d-%m %H:%M:%S.%e] [%^%l%$] %v ");

#ifdef DEBUG_LOG
	spdlog::set_pattern("[%Y-%d-%m %H:%M:%S.%e] [thread %t] [%^%l%$] %v ");
#endif

	// The default spdlog sink never flushes on its own, and when stdout is
	// piped (docker/start.sh, not a tty) libc fully buffers it. On a quiet
	// server that buffer can sit unflushed for a full day, and if the
	// process dies by signal instead of exiting cleanly, everything in it
	// is lost. Flush on every message and as a time-based backstop so a
	// crash always leaves a trace on disk.
	spdlog::flush_on(spdlog::level::info);
	spdlog::flush_every(std::chrono::seconds(2));
}

Logger &LogWithSpdLog::getInstance() {
	return inject<Logger>();
}

void LogWithSpdLog::setLevel(const std::string &name) {
	debug("Setting log level to: {}.", name);
	auto level = spdlog::level::from_str(name);
	spdlog::set_level(level);
}

std::string LogWithSpdLog::getLevel() const {
	auto level = spdlog::level::to_string_view(spdlog::get_level());
	return std::string { level.begin(), level.end() };
}

void LogWithSpdLog::log(const std::string &lvl, const fmt::basic_string_view<char> msg) const {
	spdlog::log(spdlog::level::from_str(lvl), msg);
}
