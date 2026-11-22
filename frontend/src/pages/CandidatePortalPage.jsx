import { useEffect, useState } from "react";
import { api } from "../services/api";
export default function CandidatePortalPage(){
 const [jobs,setJobs]=useState([]),[applications,setApplications]=useState([]),[selected,setSelected]=useState(""),[phone,setPhone]=useState(""),[details,setDetails]=useState(""),[consent,setConsent]=useState(false),[resume,setResume]=useState(null),[message,setMessage]=useState(""),[error,setError]=useState("");
 async function load(){try{const [j,a]=await Promise.all([api.getPublicJobs(),api.getMyApplications()]);setJobs(j);setApplications(a);}catch(e){setError(e.message);}}
 useEffect(()=>{load();},[]);
 async function apply(e){e.preventDefault();setError("");setMessage("");try{const application=await api.applyForJob({job_id:selected,phone,details:details?{notes:details}:{},email_consent:consent});if(resume) await api.uploadMyResume(application.id,resume);setMessage("Application submitted.");setSelected("");setResume(null);await load();}catch(e){setError(e.message);}}
 function logout(){localStorage.removeItem("hireflow.accessToken");localStorage.removeItem("hireflow.role");location.href="/login";}
 return <main style={{maxWidth:900,margin:"40px auto",padding:24}}><header style={{display:"flex",justifyContent:"space-between"}}><div><p className="eyebrow">CANDIDATE PORTAL</p><h1>Find your next opportunity</h1></div><button onClick={logout}>Log out</button></header>
 <section><h2>Open positions</h2>{jobs.length?jobs.map(j=><article key={j.id} style={{padding:16,border:"1px solid var(--border)",borderRadius:12,marginBottom:12}}><h3>{j.title}</h3><p>{j.department} · {j.location} · {j.employment_type}</p><p>{j.description}</p><button onClick={()=>setSelected(j.id)}>Apply for this job</button></article>):<p>No published jobs at the moment.</p>}</section>
 {selected&&<form onSubmit={apply} style={{display:"grid",gap:12,maxWidth:520}}><h2>Application details</h2><input placeholder="Phone number" value={phone} onChange={e=>setPhone(e.target.value)}/><textarea placeholder="Additional information" value={details} onChange={e=>setDetails(e.target.value)}/><label>Upload CV (PDF, DOCX, or TXT, max 10 MB)<input required type="file" accept=".pdf,.docx,.txt" onChange={e=>setResume(e.target.files?.[0]||null)}/></label><label><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/> I agree to receive application-related emails.</label><button className="button button-primary">Submit application</button></form>}
 <section><h2>My applications</h2>{applications.map(a=><article key={a.id} style={{padding:12,borderBottom:"1px solid var(--border)"}}><strong>{a.job_title}</strong><p>Status: {a.status} · Applied: {new Date(a.applied_at).toLocaleDateString()}</p></article>)}</section>
 {message&&<p role="status">{message}</p>}{error&&<p role="alert" style={{color:"crimson"}}>{error}</p>}
 </main>;
}
