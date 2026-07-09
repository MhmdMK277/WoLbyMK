export namespace main {
	
	export class Schedule {
	    mode: string;
	    days: number[];
	    time: string;
	    date: string;
	    fired: boolean;
	
	    static createFrom(source: any = {}) {
	        return new Schedule(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.mode = source["mode"];
	        this.days = source["days"];
	        this.time = source["time"];
	        this.date = source["date"];
	        this.fired = source["fired"];
	    }
	}
	export class Device {
	    name: string;
	    mac: string;
	    host: string;
	    port: number;
	    ip: string;
	    servicePort: string;
	    secureon: string;
	    username: string;
	    credHint: string;
	    cmdShutdown: string;
	    cmdSleep: string;
	    agentPort: number;
	    agentToken: string;
	    autowake: boolean;
	    schedule?: Schedule;
	
	    static createFrom(source: any = {}) {
	        return new Device(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.name = source["name"];
	        this.mac = source["mac"];
	        this.host = source["host"];
	        this.port = source["port"];
	        this.ip = source["ip"];
	        this.servicePort = source["servicePort"];
	        this.secureon = source["secureon"];
	        this.username = source["username"];
	        this.credHint = source["credHint"];
	        this.cmdShutdown = source["cmdShutdown"];
	        this.cmdSleep = source["cmdSleep"];
	        this.agentPort = source["agentPort"];
	        this.agentToken = source["agentToken"];
	        this.autowake = source["autowake"];
	        this.schedule = this.convertValues(source["schedule"], Schedule);
	    }
	
		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}
	export class HistoryEntry {
	    id: number;
	    ts: string;
	    device: string;
	    mac: string;
	    target: string;
	    result: string;
	    ping?: boolean;
	
	    static createFrom(source: any = {}) {
	        return new HistoryEntry(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.id = source["id"];
	        this.ts = source["ts"];
	        this.device = source["device"];
	        this.mac = source["mac"];
	        this.target = source["target"];
	        this.result = source["result"];
	        this.ping = source["ping"];
	    }
	}
	export class ImportResult {
	    ok: boolean;
	    error: string;
	    devices: Device[];
	
	    static createFrom(source: any = {}) {
	        return new ImportResult(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.ok = source["ok"];
	        this.error = source["error"];
	        this.devices = this.convertValues(source["devices"], Device);
	    }
	
		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}
	export class Response {
	    ok: boolean;
	    error: string;
	
	    static createFrom(source: any = {}) {
	        return new Response(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.ok = source["ok"];
	        this.error = source["error"];
	    }
	}
	
	export class Settings {
	    watchTimeout: number;
	    watchInterval: number;
	    sendCount: number;
	    sendInterval: number;
	    stagger: number;
	
	    static createFrom(source: any = {}) {
	        return new Settings(source);
	    }
	
	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.watchTimeout = source["watchTimeout"];
	        this.watchInterval = source["watchInterval"];
	        this.sendCount = source["sendCount"];
	        this.sendInterval = source["sendInterval"];
	        this.stagger = source["stagger"];
	    }
	}

}

