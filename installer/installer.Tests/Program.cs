using System.Net;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Thuai10.Launcher.Services;

if (args.Length == 2 && args[0] == "--mock-server")
{
    using TcpListener mock = new(IPAddress.Loopback, int.Parse(args[1]));
    mock.Start();
    await Task.Delay(Timeout.InfiniteTimeSpan);
    return;
}

byte[] original = Encoding.UTF8.GetBytes(new string('A', 100_000));
byte[] updated = Encoding.UTF8.GetBytes(new string('B', 100_000));
await using TestServer server = new(original);
string root = Path.Combine(Path.GetTempPath(), "thuai10-package-test-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
try
{
    PackageService service = new();
    string url = server.BaseUrl + "catalog.json";
    PackageCheck first = await service.CheckAsync(url, root, CancellationToken.None);
    Assert(first.Changes.Count == 1, "first check finds file");

    string partial = Path.Combine(root, "bin", "game.dat.part");
    Directory.CreateDirectory(Path.GetDirectoryName(partial)!);
    await File.WriteAllBytesAsync(partial, original[..10_000]);
    await service.InstallAsync(first, root, new ProgressSink(), CancellationToken.None);
    Assert(server.RangeRequests > 0, "range resume used");
    Assert(File.ReadAllBytes(Path.Combine(root, "bin", "game.dat")).SequenceEqual(original), "download hash matches");
    Assert((await service.CheckAsync(url, root, CancellationToken.None)).Changes.Count == 0, "installed file is current");

    await File.WriteAllTextAsync(Path.Combine(root, "bin", "game.dat"), "my AI changes");
    server.Content = updated;
    PackageCheck second = await service.CheckAsync(url, root, CancellationToken.None);
    Assert(second.Changes.Count == 1 && second.Changes[0].IsModifiedByUser, "local changes detected");
    await service.InstallAsync(second, root, new ProgressSink(), CancellationToken.None);
    Assert(await File.ReadAllTextAsync(Path.Combine(root, "bin", "game.dat")) == "my AI changes", "local changes retained");

    server.Content = original;
    string pausedRoot = Path.Combine(root, "pause-case");
    PackageCheck pauseCheck = await service.CheckAsync(url, pausedRoot, CancellationToken.None);
    using CancellationTokenSource pause = new();
    bool cancelled = false;
    try
    {
        await service.InstallAsync(pauseCheck, pausedRoot,
            new ProgressSink(p => { if (p.Received > 0) pause.Cancel(); }), pause.Token);
    }
    catch (OperationCanceledException) { cancelled = true; }
    string pausedPart = Path.Combine(pausedRoot, "bin", "game.dat.part");
    Assert(cancelled && File.Exists(pausedPart) && new FileInfo(pausedPart).Length > 0,
        "pause retains partial bytes");
    int beforeResume = server.RangeRequests;
    await service.InstallAsync(await service.CheckAsync(url, pausedRoot, CancellationToken.None),
        pausedRoot, new ProgressSink(), CancellationToken.None);
    Assert(server.RangeRequests > beforeResume, "paused download resumes with byte range");

    using TcpListener freePortProbe = new(IPAddress.Loopback, 0);
    freePortProbe.Start();
    int port = ((IPEndPoint)freePortProbe.LocalEndpoint).Port;
    freePortProbe.Stop();
    string launcherRoot = AppContext.BaseDirectory;
    string launchConfigPath = System.IO.Path.Combine(launcherRoot, "thuai10-launch.json");
    try
    {
        await File.WriteAllTextAsync(launchConfigPath, JsonSerializer.Serialize(new LaunchConfig
        {
            Port = port,
            ReadyTimeoutSeconds = 10,
            Server = new LaunchProgram
            {
                Path = System.IO.Path.GetFileName(Environment.ProcessPath!),
                Arguments = new() { "--mock-server", "{port}" }
            }
        }));
        using LaunchService launcher = new();
        await launcher.StartAsync(launcherRoot, CancellationToken.None);
        Assert(launcher.IsRunning, "server process launched and port became ready");
        launcher.Stop();
        Assert(!launcher.IsRunning, "server process stopped");
    }
    finally
    {
        File.Delete(launchConfigPath);
    }

    server.Path = "../outside.dat";
    bool rejected = false;
    try { await service.CheckAsync(url, root, CancellationToken.None); }
    catch (InvalidDataException) { rejected = true; }
    Assert(rejected, "path traversal rejected");
    Console.WriteLine("PASS: resume, pause, hash, update check, local protection, unsafe path, launch/stop");
}
finally
{
    Directory.Delete(root, true);
}

static void Assert(bool condition, string message)
{
    if (!condition) throw new Exception("FAIL: " + message);
}

sealed class ProgressSink(Action<(string File, long Received, long Total)>? callback = null)
    : IProgress<(string File, long Received, long Total)>
{
    public void Report((string File, long Received, long Total) value) => callback?.Invoke(value);
}

sealed class TestServer : IAsyncDisposable
{
    private readonly TcpListener listener;
    private readonly CancellationTokenSource cancellation = new();
    private readonly Task loop;
    private byte[] content;

    public TestServer(byte[] content)
    {
        this.content = content;
        listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        BaseUrl = $"http://127.0.0.1:{((IPEndPoint)listener.LocalEndpoint).Port}/";
        loop = RunAsync();
    }

    public string BaseUrl { get; }
    public string Path { get; set; } = "bin/game.dat";
    public int RangeRequests { get; private set; }
    public byte[] Content { set => content = value; }

    private async Task RunAsync()
    {
        while (!cancellation.IsCancellationRequested)
        {
            TcpClient socket;
            try { socket = await listener.AcceptTcpClientAsync(cancellation.Token); }
            catch (OperationCanceledException) { break; }
            _ = Task.Run(() => ServeAsync(socket));
        }
    }

    private async Task ServeAsync(TcpClient socket)
    {
        using (socket)
        {
            NetworkStream stream = socket.GetStream();
            using StreamReader reader = new(stream, Encoding.ASCII, leaveOpen: true);
            string? request = await reader.ReadLineAsync();
            long start = 0;
            while (await reader.ReadLineAsync() is { } line && line.Length > 0)
            {
                if (line.StartsWith("Range: bytes=", StringComparison.OrdinalIgnoreCase))
                {
                    start = long.Parse(line[13..].Split('-')[0]);
                    RangeRequests++;
                }
            }

            byte[] body;
            string headers;
            if (request?.Contains("catalog.json") == true)
            {
                body = JsonSerializer.SerializeToUtf8Bytes(new PackageCatalog
                {
                    Version = "test",
                    Files = new() { new PackageFile
                    {
                        Path = Path,
                        Url = "file.dat",
                        Size = content.LongLength,
                        Sha256 = Convert.ToHexStringLower(SHA256.HashData(content))
                    } }
                });
                headers = $"HTTP/1.1 200 OK\r\nContent-Length: {body.Length}\r\nConnection: close\r\n\r\n";
            }
            else
            {
                body = content[(int)start..];
                headers = start > 0
                    ? $"HTTP/1.1 206 Partial Content\r\nContent-Range: bytes {start}-{content.Length - 1}/{content.Length}\r\nContent-Length: {body.Length}\r\nConnection: close\r\n\r\n"
                    : $"HTTP/1.1 200 OK\r\nContent-Length: {body.Length}\r\nConnection: close\r\n\r\n";
            }

            await stream.WriteAsync(Encoding.ASCII.GetBytes(headers));
            await stream.WriteAsync(body);
        }
    }

    public async ValueTask DisposeAsync()
    {
        cancellation.Cancel();
        listener.Stop();
        await loop;
        cancellation.Dispose();
    }
}
